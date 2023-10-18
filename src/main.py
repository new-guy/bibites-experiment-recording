import argparse
import json
import re
import datetime
import os
import zipfile
import shutil
import time

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

TEMP_PATH = "./temp_unzipped_save"
PELLET_MATERIALS = ['Plant', 'Meat']

def load_unclean_json_string(input_str):
    # Remove non-printable characters and weird whitespace
    cleaned_str = re.sub(r'[^\x20-\x7E]', '', input_str)
    
    # Try to parse the cleaned string as JSON
    try:
        data = json.loads(cleaned_str)
        return data
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        return None
    
class Settings:
    def __init__(self, savedir):
        with open(savedir + "/settings.bb8settings") as settings_file:
            data = settings_file.read()
            settings_data = load_unclean_json_string(data)

        self.materials = settings_data['materials']
        self.scenario = settings_data['zones'][0]["name"].split(" ")[0]
        self.run_num = settings_data['zones'][0]["name"].split(" ")[1]

class SpeciesRecords:
    def __init__(self, savedir):
        with open(savedir + "/speciesData.json") as species_file:
            data = species_file.read()
            records = load_unclean_json_string(data)["recordedSpecies"]
        
        self.species = {}
        for record in records:
            self.species[f"id{record['speciesID']}"] = record
        
    def getSpeciesNameByID(self, speciesID):
        id_string = f"id{speciesID}"
        
        species = self.species[id_string]
        name = f"{species['genericName']} {species['specificName']}"

        return name

# define a class for a scene
class Scene:
    def __init__(self, settings, savedir):
        self.settings = settings

        # pellets
        with open(savedir + "/pellets.bb8scene") as pellet_file:
            data = pellet_file.read()
            pellet_data = load_unclean_json_string(data)

        self.pellets = {}
        for pellet_material in PELLET_MATERIALS:
            count, energy = self.get_pellet_count_and_energy_by_material(pellet_material, pellet_data)
            self.pellets[pellet_material] = {'count': count, 'energy': energy}

        # scene
        with open(savedir + "/scene.bb8scene") as scene_file:
            data = scene_file.read()
            scene_data = load_unclean_json_string(data)
        self.simulatedTime = scene_data['simulatedTime']


        # bibites
        self.speciesRecords = SpeciesRecords(savedir)
        self.species = self.aggregate_species_data(savedir)


    def __str__(self):
        simulatedTimeString = datetime.timedelta(seconds=self.simulatedTime)
        string = f"Scene:\nSimulated Time: {simulatedTimeString}\n\n"
        for pellet_material in self.pellets:
            string += f"{pellet_material} pellets: {self.pellets[pellet_material]['count']}\n"
            string += f"{pellet_material} energy: {self.pellets[pellet_material]['energy']}\n"
            string += "\n"
        
        for species_name in self.species:
            string += f"{species_name} count: {self.species[species_name]['count']}\n"
            string += f"{species_name} total energy: {self.species[species_name]['totalEnergy']}\n"
            string += "\n"
        
        return string
    
    def get_pellet_count_and_energy_by_material(self, material, pellet_zones):
        count = 0
        energy = 0

        material_settings = self.settings.materials[f"{material}Settings"]

        for zone in pellet_zones['pellets']:
            zone_pellets = zone['pellets']
            for pellet in zone_pellets:
                pellet_data = pellet['pellet']
                if pellet_data['material'] == material:
                    count += 1
                    energy += material_settings['energyDensity'] * pellet_data['amount']
        
        return count, energy

    def aggregate_species_data(self, savedir):
        species = {}

        for filename in os.listdir(savedir + "/bibites"):
            if filename.endswith('.bb8'):
                with open(savedir + "/bibites/" + filename) as bibite_file:
                    data = bibite_file.read()
                    bibite_data = load_unclean_json_string(data)

                bibit_id = bibite_data["genes"]["speciesID"]
                bibite_name = self.speciesRecords.getSpeciesNameByID(bibit_id)

                bibite_total_energy = bibite_data["body"]["totalEnergy"]
                
                if bibite_name not in species:
                    species[bibite_name] = {'count': 0, 'totalEnergy': 0, 'dietTotal': 0, 'sizeTotal': 0, 'speedTotal': 0, 'viewAngleTotal': 0, 'viewRadiusTotal': 0, 'birthMaturityTotal': 0}
                
                species[bibite_name]['count'] += 1
                species[bibite_name]['totalEnergy'] += bibite_total_energy
                species[bibite_name]['dietTotal'] += bibite_data["genes"]["genes"]["Diet"]
                species[bibite_name]['sizeTotal'] += bibite_data["genes"]["genes"]["SizeRatio"]
                species[bibite_name]['speedTotal'] += bibite_data["genes"]["genes"]["SpeedRatio"]
                species[bibite_name]['viewAngleTotal'] += bibite_data["genes"]["genes"]["ViewAngle"]
                species[bibite_name]['viewRadiusTotal'] += bibite_data["genes"]["genes"]["ViewRadius"]
                species[bibite_name]['birthMaturityTotal'] += (bibite_data["genes"]["genes"]["HatchTime"] / bibite_data["genes"]["genes"]["BroodTime"]) ** 2
        
        for species_name in species:
            species[species_name]['avgDiet'] = species[species_name]['dietTotal'] / species[species_name]['count']
            species[species_name]['avgSize'] = species[species_name]['sizeTotal'] / species[species_name]['count']
            species[species_name]['avgSpeed'] = species[species_name]['speedTotal'] / species[species_name]['count']
            species[species_name]['avgViewAngle'] = species[species_name]['viewAngleTotal'] / species[species_name]['count']
            species[species_name]['avgViewRadius'] = species[species_name]['viewRadiusTotal'] / species[species_name]['count']
            species[species_name]['avgBirthMaturity'] = species[species_name]['birthMaturityTotal'] / species[species_name]['count']
        
        return species

def init_influx_client():
    with open("./config.json") as config_file:
        data = config_file.read()
        influx_config = load_unclean_json_string(data)
    
    url = influx_config["url"]
    token = influx_config["token"]
    org = influx_config["org"]
    bucket = influx_config["bucket"]

    client = InfluxDBClient(url=url, token=token, org=org)

    return client, bucket, org

def write_to_influx(scene, settings, client, bucket, org):
    write_api = client.write_api(write_options=SYNCHRONOUS)
    for species_name in scene.species:
        species_data = scene.species[species_name]
        census_point = (
            Point("census")
            .tag("scenario", settings.scenario)
            .tag("run", settings.run_num)
            .tag("species", species_name)
            .field("count", species_data["count"])
            .field("totalEnergy", species_data["totalEnergy"])
            .field("avgDiet", species_data["avgDiet"])
            .field("avgSize", species_data["avgSize"])
            .field("avgSpeed", species_data["avgSpeed"])
            .field("avgViewAngle", species_data["avgViewAngle"])
            .field("avgViewRadius", species_data["avgViewRadius"])
            .field("avgBirthMaturity", species_data["avgBirthMaturity"])
        )

        write_api.write(bucket, org, census_point)

    for pellet_material in scene.pellets:
        pellet_data = scene.pellets[pellet_material]
        pellet_point = (
            Point("pellets")
            .tag("scenario", settings.scenario)
            .tag("run", settings.run_num)
            .tag("material", pellet_material)
            .field("count", pellet_data["count"])
            .field("energy", pellet_data["energy"])
        )

        write_api.write(bucket, org, pellet_point)


def process_save_dir(savedir, client, bucket, org):
    # read scene.bb8scene as a json file into an object from the save dir
    settings = Settings(savedir)
    scene = Scene(settings, savedir)
    write_to_influx(scene, settings, client, bucket, org)
    client.close()

def process_zipped_save(zippath):
    client, bucket, org = init_influx_client()

    #rmtree if TEMP_PATH exists
    if os.path.exists(TEMP_PATH):
        shutil.rmtree(TEMP_PATH)

    with zipfile.ZipFile(zippath, 'r') as zip_ref:
        zip_ref.extractall(TEMP_PATH)

    process_save_dir(TEMP_PATH, client, bucket, org)

class ZippedAutosaveHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return None
        elif event.event_type == 'created':
            print(f"Found new autosave: {event.src_path}")
            time.sleep(5)
            process_zipped_save(event.src_path)
            print(f"Sent new autosave to InfluxDB")

def main(autosaves_path):
    event_handler = ZippedAutosaveHandler()
    observer = Observer()
    observer.schedule(event_handler, path=autosaves_path, recursive=False)

    print(f"Watching {autosaves_path} for new autosaves...")

    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    
    observer.join()

# run main
if __name__ == "__main__":
    with open("./config.json") as config_file:
        data = config_file.read()
        autosave_path = load_unclean_json_string(data)['autosavePath']
    main(autosave_path)