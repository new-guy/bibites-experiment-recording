import json
import re
import datetime
import os
import zipfile
import shutil
import time
from statistics import mean, median

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objects as go

TEMP_PATH = "./temp_unzipped_save"
PELLET_MATERIALS = ['Plant', 'Meat']
TARGET_EXPERIMENT = ""
TARGET_RUN = ""

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
                    species[bibite_name] = {'count': 0, 'totalEnergy': 0, 'gene_lists': {}}
                
                species[bibite_name]['count'] += 1
                species[bibite_name]['totalEnergy'] += bibite_total_energy

                for gene_name in bibite_data["genes"]["genes"]:
                    if gene_name not in species[bibite_name]['gene_lists']:
                        species[bibite_name]['gene_lists'][gene_name] = []
                    
                    gene_value = bibite_data["genes"]["genes"][gene_name]
                    species[bibite_name]['gene_lists'][gene_name].append(gene_value)
                    # Store all of the gene values for this species in a list so that we can do work on it later
        
        #Calculate Gene info
        for species_name in species:
            species_data = species[species_name]
            species[species_name]["gene_data"] = {}
            for gene_name in species_data['gene_lists']:
                gene_values = species_data['gene_lists'][gene_name]
                species[species_name]["gene_data"][gene_name] = {
                    "mean": mean(gene_values),
                    "median": median(gene_values),
                    "min": min(gene_values),
                    "max": max(gene_values)
                }
        
        return species


graph_data = {
    'simTime': [],
    'plantPelletCount': [],
    'meatPelletCount': []
}

app = dash.Dash(__name__)
def initialize_graphs():
    app.layout = html.Div([
        html.H1("Bibite Analytics"),
        html.H2(f"Scenario {TARGET_EXPERIMENT} Run {TARGET_RUN}"),

        dcc.Graph(
            id="pellet-counts",
            figure={
                'data': [
                    go.Scatter(x=graph_data['simTime'], y=graph_data['plantPelletCount'], mode='lines+markers', name='Plant'),
                    go.Scatter(x=graph_data['simTime'], y=graph_data['meatPelletCount'], mode='lines+markers', name='Meat')
                ],
                'layout': {
                    'title': "Pellet Counts",
                    'xaxis': {
                        'title': "Simulated Time (seconds)"
                    },
                    'yaxis': {
                        'title': "Pellet Count"
                    }
                }
            }
        )
    ])

    app.run_server(debug=True, use_reloader=False)

def update_graphs(scene, settings):
    # Y is going to be the simulated time
    # X is going to be the count of pellets to start off with
    # Add additional charts later
    # Just for Scenario Control and Run 1 for now
    if settings.scenario != TARGET_EXPERIMENT or str(settings.run_num) != str(TARGET_RUN):
        return None
    
    plant_data = scene.pellets['Plant']
    graph_data['simTime'].append(scene.simulatedTime)
    graph_data['plantPelletCount'].append(plant_data['count'])

    meat_data = scene.pellets['Meat']
    graph_data['meatPelletCount'].append(meat_data['count'])


def process_zipped_save(zippath):
    #rmtree if TEMP_PATH exists
    if os.path.exists(TEMP_PATH):
        shutil.rmtree(TEMP_PATH)

    with zipfile.ZipFile(zippath, 'r') as zip_ref:
        zip_ref.extractall(TEMP_PATH)

    settings = Settings(TEMP_PATH)
    scene = Scene(settings, TEMP_PATH)

    update_graphs(scene, settings)

class ZippedAutosaveHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return None
        elif event.event_type == 'created':
            print(f"Found new autosave: {event.src_path}")
            time.sleep(20)
            try:
                process_zipped_save(event.src_path)
                print(f"Sent new autosave to InfluxDB")
            except Exception as e:
                print(f"Error processing autosave")
                print(e)

def main(autosaves_path):
    initialize_graphs()
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
        savefile_archive_path = load_unclean_json_string(data)['savefileArchivePath']
        TARGET_EXPERIMENT = load_unclean_json_string(data)['experimentName']
        TARGET_RUN = load_unclean_json_string(data)['runNumber']

    for filename in os.listdir(savefile_archive_path):
        if filename.endswith('.zip'):
            process_zipped_save(savefile_archive_path + "/" + filename)

    main(autosave_path)