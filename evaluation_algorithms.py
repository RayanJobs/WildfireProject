import argparse
import json
import os
import time
from typing import Optional

from generate_ignition_points import load_ignition_points
from sb3_contrib import TRPO, MaskablePPO
from sb3_contrib.common.maskable.utils import get_action_masks
from stable_baselines3 import A2C, DQN, PPO

from WISE.gym_env import FireEnv
from WISE.baselines import (
    HumanExpertAlgorithm,
    HumanInputAlgorithm,
    NaiveAlgorithm,
    NoAlgorithm,
    RandomAlgorithm,
)
from WISE.helpers import IgnitionPoint, IgnitionPoints
from WISE.results import WISE
from WISE.rewards import REWARD_FUNCTIONS
from WISE.video_recorder import WISE
import numpy as np

# Map name to ignition point and steps before simulation and steps per action
MAP_TO_IGNITION_POINTS = {
    "Sub20x20": IgnitionPoints(points=[IgnitionPoint(idx=372, year=1, x=11, y=18)]),
    "Sub40x40": IgnitionPoints(points=[IgnitionPoint(idx=909, year=1, x=28, y=22)]),
}
MAP_TO_EXTRA_KWARGS = {
    "Sub20x20": {"steps_before_sim": 20, "steps_per_action": 8},
    "Sub40x40": {"steps_before_sim": 25, "steps_per_action": 5},
    "mit_m": {"steps_before_sim": 25, "steps_per_action": 5},
    "mit_i": {"steps_before_sim": 25, "steps_per_action": 5},
    "mit_t": {"steps_before_sim": 25, "steps_per_action": 5},
    "dogrib_c1": {"steps_before_sim": 25, "steps_per_action": 5},
    "dogrib_c2": {"steps_before_sim": 25, "steps_per_action": 5},
    "dogrib_c3": {"steps_before_sim": 25, "steps_per_action": 5},
    "dogrib": {"steps_before_sim": 25, "steps_per_action": 5},
}

SB3_ALGO_TO_MODEL_CLASS = {
    "a2c": A2C,
    "ppo": PPO,
    "trpo": TRPO,
    "dqn": DQN,
    "ppo-maskable": MaskablePPO,
}
NO_MODEL_ALGO_TO_CLASS = {
    "random": RandomAlgorithm,
    "naive": NaiveAlgorithm,
    "human": HumanInputAlgorithm,
    "expert": HumanExpertAlgorithm,
    "none": NoAlgorithm,
}

SUPPORTED_ALGOS = list(SB3_ALGO_TO_MODEL_CLASS.keys()) + list(
    NO_MODEL_ALGO_TO_CLASS.keys()
)


def _get_model(algo: str, model_path: Optional[str], env: FireEnv):
    """Get the model for the given algorithm."""
    if algo in NO_MODEL_ALGO_TO_CLASS:
        return NO_MODEL_ALGO_TO_CLASS[algo](env)
    elif algo in SB3_ALGO_TO_MODEL_CLASS:
        if not os.path.exists(model_path):
            raise ValueError(f"Model path {model_path} does not exist")
        return SB3_ALGO_TO_MODEL_CLASS[algo].load(model_path)
    else:
        raise NotImplementedError(f"Algo {algo} not supported")


def main(args):
    assert args.num_iters >= 1, "Must have at least one evaluation iteration"
    if args.disable_render:
        assert args.disable_video, "Must disable video if rendering is disabled"

    # Extract ignition points
    if not args.ignition_type.endswith(".json"):
        assert args.ignition_type in {"random", "fixed"}
        ignition_points = None
    else:
        assert args.ignition_type.startswith(
            args.map
        ), "Map must match ignition point JSON"
        ignition_points = load_ignition_points(args.ignition_type)
        args.num_iters = len(ignition_points)
        print(f"WARNING! Overriding number of iterations to {args.num_iters}")

    outdir = os.environ["TMPDIR"] if "TMPDIR" in os.environ.keys() else args.output_dir

    steps_before_sim = args.steps_before_sim
    if steps_before_sim == -1:
        steps_before_sim = MAP_TO_EXTRA_KWARGS[args.map]["steps_before_sim"]

    steps_per_action = args.steps_per_action
    if steps_per_action == -1:
        steps_per_action = MAP_TO_EXTRA_KWARGS[args.map]["steps_per_action"]

    env = FireEnv(
        action_type=args.action_space,
        fire_map=args.map,
        output_dir=outdir,
        max_steps=2000,
        ignition_points=(
            MAP_TO_IGNITION_POINTS[args.map] if args.ignition_type == "fixed" else None
        ),
        action_diameter=args.action_diameter,
        steps_before_sim=steps_before_sim,
        steps_per_action=steps_per_action,
        reward_func_cls=REWARD_FUNCTIONS[args.reward],
    )

    model = _get_model(algo=args.algo, model_path=args.model_path, env=env)
    video_recorder = FirehoseVideoRecorder(
        env, args=args, disable_video=args.disable_video
    )

    if "CnnPolicy" in type(model.policy).__name__:
        env.observation_type = "forest_rgb"
        env._set_observation_space()
        print("Updated observation space to forest_rgb")

    results = FirehoseResults.from_env(env, args)

    def get_action():
        if args.algo == "ppo-maskable":
            action_masks = get_action_masks(env)
            action_, states_ = model.predict(
                obs, deterministic=True, action_masks=action_masks
            )
        else:
            action_, states_ = model.predict(obs, deterministic=True)

        action_ = int(action_)
        return action_

    all_parallel_images = []
    for episode_idx in range(args.num_iters):
        parallel_images = []

        if ignition_points is not None:
            points = ignition_points[episode_idx]
            print(f"For episode {episode_idx}, using ignition points:", points)
            obs = env.reset(ignition_points=points)
        else:
            obs = env.reset()
        if args.parallel_record:
            parallel_images.append(env.render(mode="rgb_array"))

        if not args.disable_render:
            env.render()

        done = False
        accum_reward = 0.0
        reward = None
        while not done:
            action = get_action()
            obs, reward, done, info = env.step(action)
            accum_reward += reward
            if args.parallel_record:
                parallel_images.append(env.render(mode="rgb_array"))
            if not args.disable_render:
                env.render()
            video_recorder.capture_frame()
            if args.delay:
                time.sleep(args.delay)

        if reward is None:
            raise RuntimeError("Reward is None. This should not happen")

        print(f"Episode {episode_idx + 1}/{args.num_iters}. Reward = {reward:.3f}")
        print("Accumulated reward:", accum_reward)
        results.append(
            reward=accum_reward,
            cells_harvested=len(env.cells_harvested),
            cells_on_fire=len(env.cells_on_fire),
            cells_burned=len(env.cells_burned),
            sim_steps=env.iter,
            ignition_points=env.ignition_points,
        )

    env.close()
    video_recorder.close()

    results.write_json()

    print("Done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-al",
        "--algo",
        default="naive",
        help="Specifies the RL algorithm to use",
        choices=set(SUPPORTED_ALGOS),
    )
    parser.add_argument(
        "-m",
        "--map",
        default="Sub40x40",
        help="Specifies the map to run the environment in",
    )
    parser.add_argument(
        "-p",
        "--model_path",
        type=str,
        help="Specifies the path to the model to evaluate",
    )
    parser.add_argument(
        "-as",
        "--action_space",
        default="flat",
        help="Action space type",
        choices=FireEnv.ACTION_TYPES,
    )
    parser.add_argument(
        "--steps_before_sim",
        type=int,
        default=-1,
        help="Number of steps before sim starts. If not specified, we will use the default value for the map",
    ),
    parser.add_argument(
        "--steps_per_action",
        type=int,
        default=-1,
        help="Number of steps per action. If not specified, we will use the default value for the map",
    )
    parser.add_argument(
        "-acd", "--action_diameter", default=1, type=int, help="Action diameter"
    )
    parser.add_argument(
        "-i",
        "--ignition_type",
        default="random",
        help="Specifies whether to use a random or fixed fire ignition point."
        "Choices: fixed, random, or specify path to a ignition point JSON file",
    )
    parser.add_argument(
        "-r",
        "--reward",
        default="FireSizeReward",
        help="Specifies the reward function to use",
        choices=set(REWARD_FUNCTIONS.keys()),
    )
    parser.add_argument(
        "--disable-video", action="store_true", help="Disable video recording"
    )
    parser.add_argument(
        "-d", "--disable-render", action="store_true", help="Disable cv2 rendering"
    )
    parser.add_argument(
        "--delay",
        default=0.0,
        type=float,
        help="Delay between steps in simulation. For visualization purposes "
        "- note: it doesn't get reflected in the video",
    )
    parser.add_argument(
        "-pr", "--parallel-record", action="store_true", help="Disable cv2 rendering"
    )
    parser.add_argument(
        "-o",
        "--output_dir",
        default=os.path.dirname(os.path.realpath(__file__)),
        help="Specifies the output directory for the simulation",
    )
    parser.add_argument(
        "-n",
        "--num-iters",
        type=int,
        default=20,
        help="Number of iterations to evaluate",
    )
    print("Args:", json.dumps(vars(parser.parse_args()), indent=2))

    args_ = parser.parse_args()
    main(args_)
