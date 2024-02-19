from colr import color

from internal.Enum import Constants

class Logger:
    def __init__(self, priority:int=0):
        self.priority=priority
        self.logs = []

        self._fatal = [5, (255,0,0), (90,0,0)]
        self._critical = [4, (255,182,0), (127,89,0)]
        self._success = [3, (57,202,0), (23,81,0)]
        self._info = [2, (0,140,255), (0,52,95)]
        self._skip = [1, (0,255,195), (0,100,77)]


    def __log(self, string:str, back:tuple, fore:tuple):
        self.logs.append(string)
        if len(self.logs) > Constants.logCount.value:
            self.logs.pop()
        print(color(string, back=back,fore=fore))


    @staticmethod
    def __formString(category:str, *args):
        return f"[{category}] "+" ".join(args)


    def skip(self, category:str, *args):
        if self._skip[0] >= self.priority:
            self.__log(self.__formString(category, *args),back=self._skip[1],fore=self._skip[2])


    def info(self, category:str, *args):
        if self._info[0] >= self.priority:
            self.__log(self.__formString(category, *args),back=self._info[1],fore=self._info[2])


    def success(self, category:str, *args):
        if self._success[0] >= self.priority:
            self.__log(self.__formString(category, *args),back=self._success[1],fore=self._success[2])


    def critical(self, category:str, *args):
        if self._critical[0] >= self.priority:
            self.__log(self.__formString(category, *args),back=self._critical[1],fore=self._critical[2])


    def fatal(self, category:str, *args):
        if self._fatal[0] >= self.priority:
            self.__log(self.__formString(category, *args),back=self._fatal[1],fore=self._fatal[2])
