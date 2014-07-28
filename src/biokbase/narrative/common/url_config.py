import os
import json

class Struct:
    def __init__(self, **args):
        self.__dict__.update(args)

try:
    nar_path = os.environ["NARRATIVEDIR"]
    config_json = open(os.path.join(nar_path, "config.json")).read()
    config = json.loads(config_json)
    url_config = config[config['config']]  #fun, right?

    URLS = Struct(**url_config)
except:
    url_dict = {
        "workspace" : "https://kbase.us/services/ws/",
        "invocation" : "https://kbase.us/services/invocation",
        "fba" : "https://kbase.us/services/KBaseFBAModeling",
        "genomeCmp" : "https://kbase.us/services/genome_comparison/jsonrpc",
        "trees" : "https://kbase.us/services/trees"
    }
    URLS = Struct(**url_dict)
