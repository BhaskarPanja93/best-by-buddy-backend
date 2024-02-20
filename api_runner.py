from internal.AutoReRun import AutoReRun
from internal.Enum import RequiredFiles

AutoReRun(
    toRun={RequiredFiles.coreFile.value: []}, toCheck=[RequiredFiles.common.value]
).start()
