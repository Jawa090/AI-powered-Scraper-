from pathlib import Path
import sys
root_dir=Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir))
from Database.repositories.scrapper_record_map import Scrapper_Record_Map_Repository
from Backend.scrappers.base import StandardRecord
from dotenv import load_dotenv
import os
import json
from openai import OpenAI

load_dotenv()

class Normalize():
    _instance = None

    def __new__(class_, *arguments, **keyarguments):
        # ensures only 1 instance of the class
        if class_._instance is None:
            class_._instance = super().__new__(class_)
        return class_._instance

    def __init__(self):
        # Initialize only once
        if not hasattr(self, "_initialized"):
            self.client = OpenAI(
                api_key=os.getenv("LLM_API_KEY"),
                base_url=os.getenv("LLM_BASE_URL")
            )
            self._initialized = True

    def create_map(self, raw_datapoint):
        # this creates the map and passes it to the DB for storage, also views it 
        print("Raw data\n")
        print(raw_datapoint)
        standard_schema = StandardRecord.model_json_schema()["properties"]
        print("Standard Schema\n")
        print(standard_schema)
        response = self.client.chat.completions.create(
            model=os.getenv("LLM_MODEL"),
            response_format={"type": "json_object"},
            temperature=0.0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a data mapping assistant. Compare the StandardRecord fields "
                        "with the user's raw_datapoint dictionary. Return a JSON object where "
                        "each key is a StandardRecord field name, and each value is the matching "
                        "key name from raw_datapoint (or null if no match exists)."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"StandardRecord schema:\n{json.dumps(standard_schema)}\n\n"
                        f"Raw_datapoint\n{json.dumps(raw_datapoint, default=str)}"
                    )
                }
            ]
        )
        map_dict = json.loads(response.choices[0].message.content)
        print("Map\n")
        print(map_dict)
        Scrapper_Record_Map_Repository.get_map(map_dict)
        return "data record gotton and saved in db"

    def normalize_data(self):
        # Normalize raw data based on the MAP in DB
        pass

normalizer = Normalize()

if __name__ == "__main__":
    normalizer.create_map({})  
