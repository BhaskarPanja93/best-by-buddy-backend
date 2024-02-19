"""
randomGenerator()
A Class containing different functions for generating different sorts of random strings


To USE:
Store the initialized class in a variable, Initialising the class needs:
    0 compulsory parameters
    0 optional parameters
Later call the required method of the variable with minimum and maximum size of the string to be generated
"""

from random import choice, randrange


class randomGenerator:
    def __init__(self):
        self.LOWER_CASE_ASCIIS = list(range(97, 122 + 1))
        self.UPPER_CASE_ASCIIS = list(range(65, 90 + 1))
        self.NUMBER_ASCIIS = list(range(48, 57 + 1))
        self.ALPHANUMERIC_ASCIIS = (
            self.LOWER_CASE_ASCIIS + self.UPPER_CASE_ASCIIS + self.NUMBER_ASCIIS
        )

    def AlphaNumeric(self, _min=10, _max=20) -> str:
        """
        Generates a string with numbers and alphabets(a-z, A-Z, 0-9)
        :param _min: Minimum possible length of generated string
        :param _max: Maximum possible length of generated string
        :return: A random string of the specified size
        """
        string = ""
        for _ in range(randrange(_min, _max)):
            string += chr(choice(self.ALPHANUMERIC_ASCIIS))
        return string

    def OnlyNumeric(self, _min=10, _max=20) -> str:
        """
        Generates a string with only numbers(0-9). Convert the string to int as needed
        :param _min: Minimum possible length of generated string
        :param _max: Maximum possible length of generated string
        :return: A random string of the specified size
        """
        string = ""
        for _ in range(randrange(_min, _max)):
            string += chr(choice(self.LOWER_CASE_ASCIIS + self.UPPER_CASE_ASCIIS))
        return string

    def OnlyAlpha(self, _min=10, _max=20) -> str:
        """
        Generates a string with only Alphabets(a-z, A-Z)
        :param _min: Minimum possible length of generated string
        :param _max: Maximum possible length of generated string
        :return: A random string of the specified size
        """
        string = ""
        for _ in range(randrange(_min, _max)):
            string += chr(choice(self.LOWER_CASE_ASCIIS + self.UPPER_CASE_ASCIIS))
        return string
