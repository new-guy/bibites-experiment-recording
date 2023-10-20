import json
import re
import io
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

with open("./config.json") as config_file:
    data = config_file.read()
    autosave_path = load_unclean_json_string(data)['autosavePath']
    TARGET_EXPERIMENT = load_unclean_json_string(data)['experimentName']
    TARGET_RUN = load_unclean_json_string(data)['runNumber']
    SAVEFILE_ARCHIVE_PATH = f"{load_unclean_json_string(data)['savefileArchivePath']}/{TARGET_EXPERIMENT}/{TARGET_RUN}"
    GENES_TO_MONITOR = load_unclean_json_string(data)['genesToMonitor']

PELLET_MATERIALS = ['Plant', 'Meat']
SPECIES_TO_MONITOR = ""
    
class Settings:
    def __init__(self, archive):
        with archive.open("settings.bb8settings") as settings_file:
            data = settings_file.read().decode("utf-8")
            settings_data = load_unclean_json_string(data)

        self.materials = settings_data['materials']
        self.scenario = settings_data['zones'][0]["name"].split(" ")[0]
        self.run_num = settings_data['zones'][0]["name"].split(" ")[1]

class SpeciesRecords:
    def __init__(self, archive):
        with archive.open("speciesData.json") as species_file:
            data = species_file.read().decode("utf-8")
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
    def __init__(self, settings, archive):
        self.settings = settings
        
        # scene
        with archive.open("scene.bb8scene") as scene_file:
            data = scene_file.read().decode("utf-8")
            scene_data = load_unclean_json_string(data)
        self.simulatedTime = scene_data['simulatedTime']
        self.totalBibiteCount = scene_data['nBibites']

        # pellets
        with archive.open("pellets.bb8scene") as pellet_file:
            data = pellet_file.read().decode("utf-8")
            pellet_data = load_unclean_json_string(data)

        self.pellets = {}
        for pellet_material in PELLET_MATERIALS:
            count, energy = self.get_pellet_count_and_energy_by_material(pellet_material, pellet_data)
            self.pellets[pellet_material] = {'count': count, 'energy': energy}

        # bibites
        self.speciesRecords = SpeciesRecords(archive)
        self.species = self.aggregate_species_data(archive)
    
    def get_pellet_count_and_energy_by_material(self, material, pellet_zones):
        count = 0
        energy = 0

        material_settings = self.settings.materials[f"{material}Settings"]

        for zone in pellet_zones['pellets']:
            pellet_zone = zone['pellets']
            for pellet in pellet_zone:
                pellet_data = pellet['pellet']
                if pellet_data['material'] == material:
                    count += 1
                    energy += material_settings['energyDensity'] * pellet_data['amount']
        
        return count, energy

    def aggregate_species_data(self, archive):
        species = {}
        bibites_dir = "bibites/"

        bibites_filenames = [name for name in archive.namelist() if (name.startswith(bibites_dir) and name.endswith('bb8'))]
        for filename in bibites_filenames:
            with archive.open(f"{filename}") as bibite_file:
                data = bibite_file.read().decode("utf-8")
                bibite_data = load_unclean_json_string(data)
            
            bibit_species_id = bibite_data["genes"]["speciesID"]
            species_name = self.speciesRecords.getSpeciesNameByID(bibit_species_id)

            if species_name not in species:
                species[species_name] = {'count': 0, 'totalEnergy': 0, 'gene_lists': {}}
            
            bibite_total_energy = bibite_data["body"]["totalEnergy"]
            species[species_name]['totalEnergy'] += bibite_total_energy
            species[species_name]['count'] += 1

            # Store all of the gene values for this species in a list so that we can do work on it later
            bibite_gene_data = bibite_data["genes"]["genes"]
            for gene_name in bibite_gene_data:
                bibite_gene_lists = species[species_name]['gene_lists']
                if gene_name not in bibite_gene_lists:
                    bibite_gene_lists[gene_name] = []

                gene_value = bibite_gene_data[gene_name]
                bibite_gene_lists[gene_name].append(gene_value)
        
        #Calculate Gene stats
        for species_name in species:
            species_data = species[species_name]
            species_data["gene_data"] = {}
            for gene_name in species_data['gene_lists']:
                gene_values = species_data['gene_lists'][gene_name]
                species_data["gene_data"][gene_name] = {
                    "mean": mean(gene_values),
                    "median": median(gene_values),
                    "min": min(gene_values),
                    "max": max(gene_values)
                }
        
        return species


graph_data = {
    'simTime': [],
    'plantPelletCount': [],
    'meatPelletCount': [],
    'plantPelletEnergy': [],
    'meatPelletEnergy': [],
    'totalBibiteCount': [],
    'species': {}
}

app = dash.Dash(__name__)
def initialize_graphs():
    dark_layout_style = {
        'backgroundColor': '#1a1a1a',
        'color': '#e6e6e6',
        'fontFamily': 'Arial',
        'body': {
            'margin': 0,
            'padding': 0
        },
        'h1': {
            'margin-top': 0,
            'padding': '10px'
        },
        'h2': {
            'margin-top': 0,
            'padding': '10px'
        }
    }

    scenario_graph_style = {
        'width': '45%',
        'height': '400px',
        'display': 'inline-block',
        'padding': '0 20px'
    }
    species_graph_style = {
        'width': '30%',
        'height': '250px',
        'display': 'inline-block',
        'padding': '0 10px'
    }
    dropdown_style = {
        'width': '50%'
    }

    app.layout = html.Div(style=dark_layout_style, children=[
        html.H1("Bibite Analytics"),
        html.H2(f"Experiment: {TARGET_EXPERIMENT} | Run #: {TARGET_RUN}"),
        dcc.Interval(
            id='interval-component',
            interval=5000,
            n_intervals=0
        ),
        dcc.Graph(
            id="pellet-count",
            style=scenario_graph_style
        ),
        dcc.Graph(
            id="pellet-energy",
            style=scenario_graph_style
        ),
        html.H2(children="All Species ever with 5+ Bibites")
    ] + [
        dcc.Graph(
            id="all-bibite-counts",
            style=scenario_graph_style
        ),
        dcc.Graph(
            id="all-bibite-total-energy",
            style=scenario_graph_style
        )
    ] + [
        html.H2(id="species-to-monitor", children=f"{SPECIES_TO_MONITOR} - Select below (type to search)"),
        dcc.Dropdown([SPECIES_TO_MONITOR], SPECIES_TO_MONITOR, id='species-dropdown', style=dropdown_style),
        dcc.Graph(
            id="bibite-count",
            style=scenario_graph_style
        ),
        dcc.Graph(
            id="bibite-energy",
            style=scenario_graph_style
        ),
    ] + [dcc.Graph(id=gene_name, style=species_graph_style) for gene_name in GENES_TO_MONITOR])

    app.run_server(debug=True, use_reloader=False)

# Callback to update the dropdown's options based on species_names
@app.callback(
    Output('species-dropdown', 'options'),
    Input('interval-component', 'n_intervals')
)
def update_dropdown(n):
    #species names from the keys in graph_data['species']
    species_names = list(graph_data['species'].keys())

    # Convert species_names to the format needed by the dropdown
    options = [{'label': name, 'value': name} for name in species_names]
    return options

@app.callback(
    Output('species-to-monitor', 'children'),
    Input('species-dropdown', 'value')
)
def update_species_to_monitor(selected_species):
    global SPECIES_TO_MONITOR
    SPECIES_TO_MONITOR = selected_species
    if selected_species is None:
        return "No species selected."
    return selected_species

outputs = [
    Output('pellet-count', 'figure'), 
    Output('pellet-energy', 'figure'), 
    Output('bibite-count', 'figure'), 
    Output('bibite-energy', 'figure')
    ] + [
        Output(gene_name, 'figure') for gene_name in GENES_TO_MONITOR
    ] + [
        Output('all-bibite-counts', 'figure'),
        Output('all-bibite-total-energy', 'figure')
    ]
@app.callback(
    outputs,
    Input('interval-component', 'n_intervals')
)
def update_graphs(n):
    global SPECIES_TO_MONITOR
    pellet_count_fig = {
        'data': [
            go.Scatter(x=graph_data['simTime'], y=graph_data['plantPelletCount'], mode='lines+markers', name='Plant'),
            go.Scatter(x=graph_data['simTime'], y=graph_data['meatPelletCount'], mode='lines+markers', name='Meat')
        ],
        'layout': {
            'title': "Pellet Count",
            'xaxis': {
                'title': "Sim Time (s)"
            },
            'yaxis': {
                'title': "Count"
            },
            'paper_bgcolor': '#1a1a1a',
            'plot_bgcolor': '#1a1a1a',
            'font': {
                'color': '#e6e6e6'
            }
        }
    }

    pellet_energy_fig = {
        'data': [
            go.Scatter(x=graph_data['simTime'], y=graph_data['plantPelletEnergy'], mode='lines+markers', name='Plant'),
            go.Scatter(x=graph_data['simTime'], y=graph_data['meatPelletEnergy'], mode='lines+markers', name='Meat')
        ],
        'layout': {
            'title': "Pellet Energy",
            'xaxis': {
                'title': "Sim Time (s)"
            },
            'yaxis': {
                'title': "Energy"
            },
            'paper_bgcolor': '#1a1a1a',
            'plot_bgcolor': '#1a1a1a',
            'font': {
                'color': '#e6e6e6'
            }
        }
    }

    if SPECIES_TO_MONITOR == "":
        if len(graph_data['species']) > 0:
            SPECIES_TO_MONITOR = list(graph_data['species'].keys())[0]  # Default to the first species in the list
        else:
            # No species yet?  Return empty graphs
            return (pellet_count_fig, pellet_energy_fig, None, None) + tuple([None for gene_name in GENES_TO_MONITOR])

    selected_species_data = graph_data['species'][SPECIES_TO_MONITOR]
    selected_species_count_fig = {
        'data': [
            go.Scatter(x=graph_data['simTime'], y=selected_species_data['count'], mode='lines+markers', name='Count')
        ],
        'layout': {
            'title': "Bibite Count",
            'xaxis': {
                'title': "Sim Time (s)"
            },
            'yaxis': {
                'title': "Count"
            },
            'paper_bgcolor': '#1a1a1a',
            'plot_bgcolor': '#1a1a1a',
            'font': {
                'color': '#e6e6e6'
            }
        }
    }

    selected_species_energy_fig = {
        'data': [
            go.Scatter(x=graph_data['simTime'], y=selected_species_data['totalEnergy'], mode='lines+markers', name='Count')
        ],
        'layout': {
            'title': "Bibite Energy",
            'xaxis': {
                'title': "Sim Time (s)"
            },
            'yaxis': {
                'title': "Energy"
            },
            'paper_bgcolor': '#1a1a1a',
            'plot_bgcolor': '#1a1a1a',
            'font': {
                'color': '#e6e6e6'
            }
        }
    }

    selected_species_gene_figs = []
    selected_species_gene_data = selected_species_data['gene_data']
    for gene_name in GENES_TO_MONITOR:
        selected_species_gene_fig = {
            'data': [
                go.Scatter(x=graph_data['simTime'], y=selected_species_gene_data[gene_name]['mean'], mode='lines+markers', name="mean"),
                go.Scatter(x=graph_data['simTime'], y=selected_species_gene_data[gene_name]['median'], mode='lines+markers', name="median"),
                go.Scatter(x=graph_data['simTime'], y=selected_species_gene_data[gene_name]['min'], mode='lines+markers', name="min"),
                go.Scatter(x=graph_data['simTime'], y=selected_species_gene_data[gene_name]['max'], mode='lines+markers', name="max")
            ],
            'layout': {
                'title': f"{gene_name}",
                'title_font': {'size': 10},
                'showlegend': False,
                'margin': {
                    'l': 30,
                    'r': 10,
                    'b': 20,
                    't': 30
                },
                'paper_bgcolor': '#1a1a1a',
                'plot_bgcolor': '#1a1a1a',
                'font': {
                    'color': '#e6e6e6'
                }
            }
        }
        selected_species_gene_figs.append(selected_species_gene_fig)
    
    # get all of the counts, total energies, and gene data from each species, with the species name as the key
    species_counts = [
        go.Scatter(x=graph_data['simTime'], y=graph_data['totalBibiteCount'], mode='lines+markers', name='Total (incl. < 5)')
    ]
    species_total_energies = []
    for species_name in graph_data['species']:
        species_data = graph_data['species'][species_name]

        # only collect species with 5+ bibites
        if max(species_data['count']) < 5:
            continue

        count_scatter = go.Scatter(x=graph_data['simTime'], y=species_data['count'], mode='lines+markers', name=species_name)
        species_counts.append(count_scatter)

        total_energy_scatter = go.Scatter(x=graph_data['simTime'], y=species_data['totalEnergy'], mode='lines+markers', name=species_name)
        species_total_energies.append(total_energy_scatter)

    all_species_count_fig = {
        'data': species_counts,
        'layout': {
            'title': "Count",
            'xaxis': {
                'title': "Sim Time (s)"
            },
            'yaxis': {
                'title': "Count"
            },
            'paper_bgcolor': '#1a1a1a',
            'plot_bgcolor': '#1a1a1a',
            'font': {
                'color': '#e6e6e6'
            }
        }
    }

    all_species_energy_fig = {
        'data': species_total_energies,
        'layout': {
            'title': "Total Energy",
            'xaxis': {
                'title': "Sim Time (s)"
            },
            'yaxis': {
                'title': "Energy"
            },
            'paper_bgcolor': '#1a1a1a',
            'plot_bgcolor': '#1a1a1a',
            'font': {
                'color': '#e6e6e6'
            }
        }
    }
    
    response = (pellet_count_fig, pellet_energy_fig, selected_species_count_fig, selected_species_energy_fig) + tuple(selected_species_gene_figs) + (all_species_count_fig, all_species_energy_fig)
    return response

def store_graph_data(scene):
    graph_data['simTime'].append(scene.simulatedTime)
    graph_data['totalBibiteCount'].append(scene.totalBibiteCount)

    plant_data = scene.pellets['Plant']
    graph_data['plantPelletCount'].append(plant_data['count'])
    graph_data['plantPelletEnergy'].append(plant_data['energy'])

    meat_data = scene.pellets['Meat']
    graph_data['meatPelletCount'].append(meat_data['count'])
    graph_data['meatPelletEnergy'].append(meat_data['energy'])

    for species_name in scene.species:
        species_data = scene.species[species_name]

        if species_name not in graph_data['species']:
            graph_data['species'][species_name] = {
                'count': [],
                'totalEnergy': [],
                'gene_data': {}
            }

        graph_species_data = graph_data['species'][species_name]
        graph_species_data['count'].append(species_data['count'])
        graph_species_data['totalEnergy'].append(species_data['totalEnergy'])

        graph_species_gene_data = graph_species_data['gene_data']
        for gene_name in species_data['gene_data']:
            if gene_name not in GENES_TO_MONITOR:
                continue
            
            gene_data = species_data['gene_data'][gene_name]
            if gene_name not in graph_species_gene_data:
                graph_species_gene_data[gene_name] = {}
                graph_species_gene_data[gene_name]['mean'] = []
                graph_species_gene_data[gene_name]['median'] = []
                graph_species_gene_data[gene_name]['min'] = []
                graph_species_gene_data[gene_name]['max'] = []
            
            graph_species_gene_data[gene_name]['mean'].append(gene_data['mean'])
            graph_species_gene_data[gene_name]['median'].append(gene_data['median'])
            graph_species_gene_data[gene_name]['min'].append(gene_data['min'])
            graph_species_gene_data[gene_name]['max'].append(gene_data['max'])


def process_zipped_save(zippath, savezip=True):
    with open(zippath, 'rb') as f:
        zip_data = io.BytesIO(f.read())

    with zipfile.ZipFile(zip_data, 'r') as archive:
        settings = Settings(archive)

        if settings.scenario != TARGET_EXPERIMENT or str(settings.run_num) != str(TARGET_RUN):
            return None

        # Process the savefile and update graphs
        scene = Scene(settings, archive)
        store_graph_data(scene)

        if savezip:
            shutil.copy2(zippath, SAVEFILE_ARCHIVE_PATH)

class ZippedAutosaveHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return None
        elif event.event_type == 'created':
            print(f"Found new autosave: {event.src_path}")
            time.sleep(5)
            try:
                process_zipped_save(event.src_path)
                print(f"Autosave processed")
            except Exception as e:
                print(f"Error processing autosave")
                print(e)

def main(autosaves_path):
    event_handler = ZippedAutosaveHandler()
    observer = Observer()
    observer.schedule(event_handler, path=autosaves_path, recursive=False)

    print(f"Watching {autosaves_path} for new autosaves...")

    observer.start()
    initialize_graphs()

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

    if not os.path.exists(SAVEFILE_ARCHIVE_PATH):
        os.makedirs(SAVEFILE_ARCHIVE_PATH)

    zip_files = [f for f in os.listdir(SAVEFILE_ARCHIVE_PATH) if f.endswith('.zip')]

    savefiles_processed = 1
    for filename in zip_files:
        process_zipped_save(SAVEFILE_ARCHIVE_PATH + "/" + filename, savezip=False)
        print(f"{savefiles_processed}/{len(zip_files)} preexisting saves added")
        savefiles_processed += 1

    main(autosave_path)