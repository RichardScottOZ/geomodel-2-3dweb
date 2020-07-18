"""
Parent Class for *_kit classes
"""
import logging
import sys

class ExportKit:

    def __init__(self, debug_level):
        ''' Initialise class
        :param debug_level: debug level taken from python's 'logging' module
        '''
        # Set up logging, use an attribute of class name so it is only called once
        if not hasattr(ExportKit, 'logger'):
            ExportKit.logger = logging.getLogger(__name__)

            # Create console handler
            handler = logging.StreamHandler(sys.stdout)

            # Create formatter
            formatter = logging.Formatter('%(asctime)s -- %(name)s -- %(levelname)s - %(message)s')

            # Add formatter to ch
            handler.setFormatter(formatter)

            # Add handler to logger and set level
            ExportKit.logger.addHandler(handler)

        # Finally, set debug level
        ExportKit.logger.setLevel(debug_level)
        self.logger = ExportKit.logger