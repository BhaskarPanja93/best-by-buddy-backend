from autoReRun import Runner as AutoReRunner
from internal.Enum import RequiredFiles

AutoReRunner({RequiredFiles.userGatewayFile.value: []}, RequiredFiles.common.value.__add__([RequiredFiles.userGatewayFile.value])).start()
