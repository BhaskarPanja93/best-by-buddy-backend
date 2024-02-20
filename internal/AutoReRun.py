"""
AutoReRun()
This class will be used to automatically kill running process(es) and re-spawn new processes for the specified files everytime a specified file(s) update.
For example, Automatically re-starting any server when the server file(s) is modified.


To USE:
Call(initialise) the class with:
    2 compulsory parameters
        toRun: should be a list of all the files that need to be re-run altogether
        toCheck: should be a list of all the files that needs to be checked for changes
    1 optional parameter
        reCheckInterval (default 1): Can be a float or integer representing the time to wait for concurrent file modification checks
Don't forget to use method `.start()` on the class you just initialised.
    E.g. Updater(["D:/internal/Server.py"], ["D:/internal/Config.py"], 2).start()
    E.g. Updater(["D:/internal/Server.py"], ["D:/internal/Config.py"]).start()
    E.g. Updater(["Server.py"], ["Config.py"]).start()
    E.g. _thread = Updater(["Server.py"], ["Config.py"])
         _thread.start()



ADVANCED:
To run any program that is not a python file, remove the keyword `executable` from the `Popen` call in `startPrograms` function and just pass the program with or without arguments
    E.g. Popen("taskkill /f /t /pid 1234", shell=choice([True, False]), stdout=subprocess.DEVNULL)
    E.g. Popen("taskkill /f /t /pid 1234")
    E.g. Popen(["taskkill /f /t /pid"]+["1234"])
"""

from subprocess import Popen
from time import sleep
from sys import executable
from threading import Thread
from os import stat


class AutoReRun(Thread):
    def __init__(
        self, toRun: dict[str, list[str]], toCheck: list, reCheckInterval: int = 1
    ):
        Thread.__init__(self)
        self.programsToRun = toRun
        self.programsToCheck = toCheck.__add__(list(toRun))
        self.currentProcesses = []
        self.reCheckInterval = reCheckInterval
        self.lastFileStat = self.fetchFileStats()
        self.startPrograms()

    def run(self):
        """
        Overriding run from threading.Thread
        Infinite Loop waiting for file updates and re-run the programs if updates found
        """
        while True:
            if self.checkForUpdates():
                self.startPrograms()
            sleep(self.reCheckInterval)

    def fetchFileStats(self) -> list:
        """
        Checks current file state
        Returns a list containing tuples containing each file and its last modified state
        If a to-be-checked file gets added, or goes missing, it is treated as a file update
        :return:
        """
        tempStats: list[tuple[str, float]] = []
        for filename in self.programsToCheck:
            try:
                tempStats.append((filename, stat(filename).st_mtime))
            except:  ## file is not present
                pass
        return tempStats

    def checkForUpdates(self) -> bool:
        """
        Checks if current file state matches old known state
        Returns a boolean if current received file state differs from the last known state
        :return:
        """
        file_stat = self.fetchFileStats()
        if self.lastFileStat != file_stat:
            self.lastFileStat = file_stat
            return True
        else:
            return False

    def startPrograms(self):
        """
        Respawns processes
        Kills last running processes if any and then respawn newer processes for each file to be run
        """
        temp = self.currentProcesses.copy()
        if temp:
            print("Killing previous state...")
        for _process in temp:
            if _process and not _process.poll():
                _process.kill()
                _process.wait()
                self.currentProcesses.remove(_process)
        sleep(2)
        for program in self.programsToRun:
            self.currentProcesses.append(
                Popen([executable, program] + self.programsToRun[program])
            )
