import re
from datetime import datetime

def revertDatetimeFormat(input_log_string: str) -> str:
    """
    Converts a datetime fromat of 'YYYY-DD-MM HH:MM:SS' to a human readable format.
    (e.g. Fri Jun 28 12:11:23 2024). This is necessary because an updated version of
    easyrsa changed the format of this string which breaks the update-manager-api. This
    is a workaround.

    :param str log_text: String whose timestamps will be converted.
    :returns: str
    """

    if isinstance(input_log_string, bytes):
        input_log_string = input_log_string.decode('utf-8')

    # The regex pattern to find the updated datetime format.
    pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'
    
    # Converts the new datetime format back to the old format.
    def convertOldDatetimeFormat(matched_str):
        datetime_str = matched_str.group(1)
        datetime_obj = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M:%S')
        return datetime_obj.strftime('%a %b %d %H:%M:%S %Y')
    
    # Replace the new datetime format with the old one.
    return re.sub(pattern, convertOldDatetimeFormat, input_log_string)
