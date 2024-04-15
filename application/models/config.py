import yaml
from schema import Schema, SchemaError

class Config:
    """
        A Config defines the basic parameters on how the application should be run
        param: file_path: the path where the configuration yaml file resides
    """
    def __init__(self, file_path: str):
        schema = Schema({
            "start_time": str,
            "garmin_api_token": str,
            "caltopo_map_id": str,
            "caltopo_session_id": str,
            "tracker_marker_name": str,
            "route_name": str,
            "aid_stations": 
                [
                    {
                        "name": str,
                        "mile_mark": float
                    }
                ]
        })
        try:
            config = self.get_config_from_file(file_path)
            schema.validate(config)
        except FileNotFoundError:
            print(f"Error: File '{file_path}' not found.")
            raise e
        except yaml.YAMLError as e:
            print(f"Error: YAML parsing error in '{file_path}': {e}")
            raise e
        except SchemaError as e:
            raise e
        self.start_time = config["start_time"]
        self.garmin_api_token = config["garmin_api_token"]
        self.caltopo_map_id = config["caltopo_map_id"]
        self.caltopo_session_id = config["caltopo_session_id"]
        self.route_name = config["route_name"]
        self.aid_stations = config["aid_stations"]
        
    def get_config_from_file(self, file_path: str): 
        """
        Reads in a yaml file and returns the dict.

        :param self: The current object
        :param str file_path: The path to the file.
        :return dict: The parsed dict from the config file.
        """
        with open(file_path, "r") as file:
            yaml_content = yaml.safe_load(file)
        return yaml_content