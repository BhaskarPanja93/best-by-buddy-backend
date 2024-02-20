from internal.AutoReRun import AutoReRun
from internal.Enum import RequiredFiles

AutoReRun({RequiredFiles.userGatewayFile.value: []}, [RequiredFiles.common.value]).start()
#AutoReRun({RequiredFiles.adminGatewayFile.value: []}, [RequiredFiles.common.value], 1).start()
