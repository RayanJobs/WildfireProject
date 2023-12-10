import logging
import time

from gym.wrappers.monitoring.video_recorder import VideoRecorder
from stable_baselines3 import PPO

from stable_baselines3 import PPO

from WISE.gym_env import FireEnv
from generator.helpers import IgnitionPoints, IgnitionPoint

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    trained_model = PPO.load("../vectorize_model_2023-05-11/ppo_final.zip")
    evaluation_env = FireEnv(ignition_points=IgnitionPoints([IgnitionPoint(1100, 1)]))
    observation = evaluation_env.reset()
    video_recorder = VideoRecorder(evaluation_env, "ppo_vid.mp4", enabled=True)

    for step in range(1000):
        action, _states = trained_model.predict(observation, deterministic=True)
        observation, reward, done, info = evaluation_env.step(action)

        evaluation_env.render()
        video_recorder.capture_frame()

        print("\n", action, reward)
        time.sleep(0.025)
        if done:
            observation = evaluation_env.reset()
            break

    video_recorder.close()
    video_recorder.enabled = False
    evaluation_env.close()
