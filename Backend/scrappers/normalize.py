from pathlib import Path
import sys
root_dir=Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir))
from Database.repositories.scrapper_record_map import Scrapper_Record_Map_Repository
from base import StandardRecord
from dotenv import load_dotenv
import os
import json
from openai import OpenAI



load_dotenv()
client=OpenAI(api_key=os.getenv("LLM_API_KEY")
                ,base_url=os.getenv("LLM_BASE_URL"))

class Normalize():
    def __init__(self):
        pass
    def create_map(raw_datapoint):
        #this creates the map and passes it to the DB for storage, also views it 
        map={}
        print("Raw data\n")
        print(raw_datapoint)
        standard_schema=StandardRecord.model_json_schema()["properties"]
        print("Standard Schema\n")
        print(standard_schema)
        response=client.chat.completions.create(
            model=os.getenv("LLM_MODEL"),
            response_format={"type": "json_object"},
            tempareture=0.0,
            message=[
                {
                    "role":"system",
                    content(
                    "You are a data mapping assistant. Compare the StandardRecord fields "
                    "with the user's raw_datapoint dictionary. Return a JSON object where "
                    "each key is a StandardRecord field name, and each value is the matching "
                    "key name from raw_datapoint (or null if no match exists)."
                    )
                },
                {
                    "role":"user",
                    content(
                        f"StandardRecord schema:\n{json.dumps(standard_schema)}\n\n"
                        f"Raw_datapoint\n{json.dumps(raw_datapoint,default=str)}"
                    )

                }

            ]


            
            

        )
        Scrapper_Record_Map_Repository.get_map(map)
        return "data record gotton and saved in db"

    def normalize_data():
        #Normalize raw data based on the MAP in DB
        pass

if __name__ == "__main__":
    Normalize.create_map({})  
