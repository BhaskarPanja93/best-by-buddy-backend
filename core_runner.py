from autoReRun import Runner as AutoReRunner
from internal.Enum import RequiredFiles

AutoReRunner(toRun={RequiredFiles.coreFile.value: []}, toCheck=RequiredFiles.common.value.__add__([RequiredFiles.coreFile.value])).start()
