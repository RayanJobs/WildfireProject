# coding: utf-8
__version__ = "1.0"
__author__ = "Cristobal Pais"
# name change to Cell2FireC_class by DLW (confusion with the dir name)

# General imporations
import os
import glob
import shutil
import signal
import subprocess
import sys
import WISE.utils.DataGeneratorC as DG
import WISE.utils.ReadDataPrometheus as RDP
from WISE.utils.ParseInputs import InitCells
from WISE.utils.Stats import *
from WISE.utils.Heuristics import *
import WISE  # for path finding

p = str(cell2fire.__path__)
l = p.find("'")
r = p.find("'", l + 1)
cell2fire_path = p[l + 1 : r]
print("cell2fire_path", cell2fire_path)


class Cell2FireC_class:
    # Constructor and initial run
    def __init__(self, args):
        # Store arguments
        self.arguments = args

        # Check if we need to generate DataC.csv
        self.generateDataC()

        # Main call
        if self.arguments.onlyProcessing is False:
            self.run()
        else:
            print(
                "Running Cell2FirePy as a post-processing tool for a previous simulation"
            )

        # Containers
        self.numCells = 0
        self.numRows = 0
        self.numCols = 0
        self.adjacentCells = {}
        self.coordCells = {}
        self.gForestType = []
        self.gForestN = []
        self.colors = {}
        self.fTypeCells = []
        self.fTypes2 = {
            "m1": 0,
            "m2": 1,
            "m3": 2,
            "m4": 3,
            "c1": 4,
            "c2": 5,
            "c3": 6,
            "c4": 7,
            "c5": 8,
            "c6": 9,
            "c7": 10,
            "d1": 11,
            "s1": 12,
            "s2": 13,
            "s3": 14,
            "o1a": 15,
            "o1b": 16,
            "d2": 17,
        }

    # Run C++ Sim
    def run(self):
        # Parse args for calling C++ via subprocess
        execArray = [
            os.path.join(cell2fire_path, "Cell2FireC/Cell2Fire"),
            "--input-instance-folder",
            self.arguments.InFolder,
            "--output-folder",
            self.arguments.OutFolder if (self.arguments.OutFolder is not None) else "",
            "--ignitions" if (self.arguments.ignitions) else "",
            "--sim-years",
            str(self.arguments.sim_years),
            "--nsims",
            str(self.arguments.nsims),
            "--grids" if (self.arguments.grids) else "",
            "--final-grid" if (self.arguments.finalGrid) else "",
            "--Fire-Period-Length",
            str(self.arguments.input_PeriodLen),
            "--output-messages" if (self.arguments.OutMessages) else "",
            "--weather",
            self.arguments.WeatherOpt,
            "--nweathers",
            str(self.arguments.nweathers),
            "--ROS-CV",
            str(self.arguments.ROS_CV),
            "--IgnitionRad",
            str(self.arguments.IgRadius),
            "--seed",
            str(int(self.arguments.seed)),
            "--nthreads",
            str(int(self.arguments.nthreads)),
            "--ROS-Threshold",
            str(self.arguments.ROS_Threshold),
            "--HFI-Threshold",
            str(self.arguments.HFI_Threshold),
            "--bbo" if (self.arguments.BBO) else "",
            "--HarvestPlan",
            self.arguments.HCells if (self.arguments.HCells is not None) else "",
            "--verbose" if (self.arguments.verbose) else "",
        ]

        # Output log
        if self.arguments.OutFolder is not None:
            if os.path.isdir(self.arguments.OutFolder) is False:
                os.makedirs(self.arguments.OutFolder)
            LogName = os.path.join(self.arguments.OutFolder, "LogFile.txt")
        else:
            LogName = os.path.join(self.arguments.InFolder, "LogFile.txt")

        # Perform the call
        print(" ".join(execArray))
        proc = subprocess.Popen(execArray)
        proc.communicate()

        return_code = proc.wait()
        if return_code != 0:
            raise RuntimeError(
                f"C++ returned {return_code}.\nTry looking at {LogName}."
            )

        # End of the replications
        print("End of Cell2FireC execution...")

    # Run C++ Sim with heuristic treatment
    def run_Heur(self, OutFolder, HarvestPlanFile):
        # Parse args for calling C++ via subprocess
        execArray = [
            os.path.join(cell2fire_path, "Cell2FireC/Cell2Fire"),
            "--input-instance-folder",
            self.arguments.InFolder,
            "--output-folder",
            OutFolder if (OutFolder is not None) else "",
            "--ignitions" if (self.arguments.ignitions) else "",
            "--sim-years",
            str(self.arguments.sim_years),
            "--nsims",
            str(self.arguments.nsims),
            "--grids" if (self.arguments.grids) else "",
            "--final-grid" if (self.arguments.finalGrid) else "",
            "--Fire-Period-Length",
            str(self.arguments.input_PeriodLen),
            "--output-messages" if (self.arguments.OutMessages) else "",
            "--weather",
            self.arguments.WeatherOpt,
            "--nweathers",
            str(self.arguments.nweathers),
            "--ROS-CV",
            str(self.arguments.ROS_CV),
            "--IgnitionRad",
            str(self.arguments.IgRadius),
            "--seed",
            str(int(self.arguments.seed)),
            "--nthreads",
            str(int(self.arguments.nthreads)),
            "--ROS-Threshold",
            str(self.arguments.ROS_Threshold),
            "--HFI-Threshold",
            str(self.arguments.HFI_Threshold),
            "--bbo" if (self.arguments.BBO) else "",
            "--HarvestPlan",
            HarvestPlanFile if (HarvestPlanFile is not None) else "",
            "--verbose" if (self.arguments.verbose) else "",
        ]

        # Output log
        if OutFolder is not None:
            if os.path.isdir(OutFolder) is False:
                os.makedirs(OutFolder)
            LogName = os.path.join(OutFolder, "LogFile.txt")
        else:
            LogName = os.path.join(self.arguments.InFolder, "LogFile.txt")

        # Perform the call
        with open(LogName, "w") as output:
            proc = subprocess.Popen(execArray, stdout=output)
            proc.communicate()
        return_code = proc.wait()

        # End of the replications
        if HarvestPlanFile is not None:
            print("End of Cell2FireC with Harvesting Plan execution...")
        else:
            print("End of Cell2FireC execution...")

    # Pre-processing
    """
    Generate the Data.csv file for the C++ core
    """

    def generateDataC(self):
        if os.path.isfile(os.path.join(self.arguments.InFolder, "DataC.csv")) is False:
            # Run script
            arguments = {}
            arguments["-input-folder"] = self.arguments.InFolder
            arguments["-output-folder"] = self.arguments.OutFolder
            arguments["-weather"] = self.arguments.WeatherOpt
            arguments["-harvest"] = self.arguments.HCells
            arguments["-max-dist"] = self.arguments.IgRadius
            arguments["-max-weather"] = self.arguments.nweathers
            arguments["-period-len"] = self.arguments.input_PeriodLen

            DataGenerator.run(arguments)
        else:
            print("DataC.csv already generated")

    # Reading Basic Data
    """
    Read and Initialize the Cell Structure
    """

    def initializeCells(self):
        """
        Initialize cell structure with M.
        """
        arguments = {}
        arguments["-input-folder"] = self.arguments.InFolder
        arguments["-output-folder"] = self.arguments.OutFolder
        arguments["-burn-buff"] = self.arguments.burnBuff
        arguments["-number-cells"] = self.arguments.number_cells
        arguments["-number-rows"] = self.arguments.number_rows
        arguments["-number-cols"] = self.arguments.number_cols
        arguments["-burn-in-years"] = self.arguments.burn_in_years
        arguments["-ignitions"] = self.arguments.ignitions
        arguments["-treatment"] = self.arguments.treatment
        arguments["-harvest"] = self.arguments.HCells
        arguments["-rain"] = self.arguments.rain
        arguments["-rain-num"] = self.arguments.rain_num

        if self.arguments.verbose:
            print("Running Data-Read")
        DG.run(arguments)

        if self.arguments.verbose:
            print("Running Data-Initialization")
        InitCells(arguments)

    # Plotting Heatmaps
    """
    Read and Initialize the Cell Structure
    """

    def plotHeatmaps(self):
        """
        Create heatmaps and save them in .png files
        """
        # Parse args for calling C++ via subprocess
        execArray = [
            os.path.join(cell2fire_path, "HeatMapTool/HeatMapTool"),
            "--input-folder",
            self.arguments.InFolder,
            "--output-folder",
            self.arguments.OutFolder,
            "--output-prefix",
            self.arguments.OutPrefix,
            "--threshold",
            str(self.arguments.ROS_Threshold),
            "--mode",
            str(self.arguments.heatmap_mode),
            "--input-ros-folder",
            self.arguments.ros_folder,
        ]

        # Output log
        if os.path.isdir(self.arguments.OutFolder) is False:
            os.makedirs(self.arguments.OutFolder)
        LogName = os.path.join(self.arguments.OutFolder, "LogFile.txt")

        # Perform the call
        with open(LogName, "w") as output:
            print(" ".join(execArray))
            proc = subprocess.Popen(execArray, stdout=output)
            proc.communicate()

        return_code = proc.wait()
        if return_code != 0:
            raise RuntimeError(f"HeatMapTool returned {return_code}.\nTry looking at {LogName}.")

        print("End of HeatMapTool execution...")

    # Rest of the class remains unchanged
