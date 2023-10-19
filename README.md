# Bibites Experiment Recording

**At the time of posting, this only supports Alpha 0.6a7** - the game is in active development, which means the save format is in active development.  Unfortunately, this means that supporting multiple versions of save formats is nontrivial.  Please feel free to submit a PR if you get it working for a different version, and I'll make a release tag for it.

Hi, I made this to record timeseries data from Bibites so that I can better understand how the different species are changing in relation to one another and the environment.  There's a lot that can be added and improved, but at the very least this gives some basic overviews of how species are changing over time.  This is set up to read data from autosaves, parse it out, then renders it on a webpage at `localhost:8050`.

I'm not a data scientist, so I'm sure there's a lot that can be improved here.  If you have any suggestions, please feel free to submit a PR or open an issue.  Also if you do figure out how to get all of this going and wanna submit a quick PR to improve these docs, that'd be cool too.

This will also save all of the files it records to a folder called `save_archive` in the root of this directory using the filepath `save_archive\[experimentName]\[runNumber]\`.  This lets you save data for later and pause and resume experiments.

Also, I use the term `experiment` to refer to any individual timeline of a run in the Bibites simulator.  Science!

### Limitations
- Can only look at data from one experiment at a time
- Can only look at one species from an experiment at a time

![image](dashboard_example.png)

## Setup - Local

**At the time of posting, this only supports Alpha 0.6a7**

If you don't know how to do any of this, you can just copy this entire setup section into chatgpt and ask it to explain how to do this like you're five.  It'll help you out.

1. Install python
2. Download this repo (either with git or by downloading the zip and extracting it)
3. Open a command prompt in the root of this directory
4. Run `pip install -r requirements.txt` (if this doesn't work, copy the error you're getting and google it and/or ask chatgpt how to fix it.  Also if you don't know how to do this, ask chatgpt and he'll help you out)
5. Create a `config.json` file in the root of this dir with the following format:
```
{
    "autosavePath": "[path to where your game autosaves]",
    "savefileArchivePath": "[path to all of your autosaves that you've archived - it will also save new autosaves here]",
    "experimentName": "[experiment to get data on]",
    "runNumber": "[run to get data on]",
    "genesToMonitor": [
        [list of genes to monitor - see reference/bibite.bb8 for a list of genes]
    ],
    "speciesToMonitor": "[name of species - note that this is sensitive to capitalization and nothing will render if this is wrong]"
}
```
for example:
```
    {
        "autosavePath": "C:\\Users\\user\\AppData\\LocalLow\\The Bibites\\The Bibites\\Savefiles\\Autosaves",
        "savefileArchivePath": "./save_archive/",
        "experimentName": "Experiment",
        "runNumber": "1",
        "genesToMonitor": [
            "Diet",
            "SizeRatio"
        ],
        "speciesToMonitor": "Basic bibite"
    }
```
6. Run `python ./src/main.py` or whatever the equivalent is for you.  Alternatively, use vscode, open up main.py, and hit F5 to run it - that's what I do
7. Go to `localhost:8050` in your browser

*NOTE* You need to name your first pellet zone in your scenario in the format `"[experimentName] [runNumber]"` for this to work.  If you don't do this, it _will break_.

## Setup - Bibites

This software will only log data from saves based upon the name of the first zone in your scenario.  It needs to be named in the format `[Scenario] [Run #]`.  If you don't do this, it _will break_.  For the above example config.js, the first zone would need to be named `Experiment 1`

This works by parsing data from autosaves, so I would recommend increasing your autosave frequency if you wanna get more granular data.

## Contributing

Check out the TODO.md!

Or make these docs better - if you run into issues and you wanna suggest how you fixed them, open up a PR and please do so!  If you don't know how to do that, hit up @newguy on the bibites discord and he'll explain it (or just google it).

Submit a PR!

If you wanna set up linting and whatnot, that'd be cool.