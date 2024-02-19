"""
mysqlPool()
AutoScaling concurrent MySQL query handler that automatically creates and re-use old connections as per situation.


To USE:
Store the initialized class in a variable, Initialising the class needs:
    4 compulsory parameters
        user: Username for the database
        password: Password for the database
        dbName: Database name
    2 optional parameters
        host (default localhost): Location where the database is hosted e.g. localhost or any specific IP
        logFile (default None): Absolute or relative text file location to write all errors raised
        errorWriter (default None): CAN BE IGNORED. A custom function that takes 3 string arguments to write and/or process logs
Later call the `execute` method with all the necessary parameters
"""

from time import sleep
import mysql.connector


class mysqlPool:
    def __init__(
        self,
        user,
        password,
        dbName,
        host="127.0.0.1",
        port=3306,
        logFile=None,
        errorWriter=None,
    ):
        self.connections = []
        self.user = user
        self.host = host
        self.port = port
        self.password = password
        self.dbName = dbName
        self.logFile = logFile
        self.errorWriter = (
            errorWriter if errorWriter is not None else self.defaultErrorWriter
        )

    def checkDatabaseStructure(self):
        """
        Override this function and implement code to check and create the database and the corresponding tables (if needed).

        Example code to create the database:
        if not self.run(f"SHOW DATABASES LIKE \"{self.db_name}\"", commit_required=False, database_required=False):
            self.execute(f"CREATE database {self.dbName};", database_required=False, commit_required=False)

        Example code to create a sample table:
        table_name = "song_data"
        if not self.run(f"SHOW TABLES LIKE \"{table_name}\"", commit_required=False):
            self.execute(f'''
                       CREATE TABLE IF NOT EXISTS `{self.db_name}`.`{table_name}` (
                       `_id` VARCHAR(100) NOT NULL,
                       `duration` INT ZEROFILL NULL,
                       `thumbnail` VARCHAR(100) NULL,
                       `audio_url` VARCHAR(2000) NULL,
                       `audio_url_created_at` TIMESTAMP NULL,
                       PRIMARY KEY (`_id`),
                       UNIQUE INDEX `_id_UNIQUE` (`_id` ASC) VISIBLE)
                       ''', commit_required=True))
        """
        pass

    def defaultErrorWriter(
        self, category: str = "", text: str = "", extras: str = "", log: bool = True
    ):
        """
        Demo(default) function to write MySQL errors to output and file
        :param category: Category of the error
        :param text: Main text of the error
        :param extras: Additional text
        :param log: Boolean specifying if the error has to be written to the file
        """
        string = f"[MYSQL POOL] [{category}]: {text} {extras}"
        # print(string)
        if log:
            open(self.logFile, "a").write(string + "\n")

    def execute(
        self, syntax: str, ignoreErrors: bool = True, dbRequired: bool = True
    ) -> None | list:
        """
        :param syntax: The MySQL syntax to execute
        :param ignoreErrors: If errors are supposed to be caught promptly or sent to the main application
        :param dbRequired: Boolean specifying if the syntax is supposed to be executed on the database or not. A database creation syntax doesn't need the database to be already present, so the argument should be False for those cases
        :return: None or list of tuples depending on the syntax passed
        """
        while True:
            try:
                if not dbRequired:
                    connection = mysql.connector.connect(
                        user=self.user,
                        host=self.host,
                        port=self.port,
                        password=self.password,
                        autocommit=True,
                    )
                elif self.connections:
                    connection = self.connections.pop()
                else:
                    connection = mysql.connector.connect(
                        user=self.user,
                        host=self.host,
                        port=self.port,
                        password=self.password,
                        database=self.dbName,
                        autocommit=True,
                    )
                break
            except Exception as e:
                self.errorWriter("CONNECTION FAIL", repr(e))
                if ignoreErrors:
                    pass
                else:
                    raise e
                sleep(1)
        connection.consume_results()
        cursor = connection.cursor()
        try:
            cursor.execute(syntax)
            data = cursor.fetchall()
        except Exception as e:
            data = None
            if ignoreErrors:
                pass
            else:
                self.errorWriter(text=repr(e), extras=syntax)
                raise e
        connection.consume_results()
        self.connections.append(connection)
        # connection.close()
        return data
