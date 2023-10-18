# Bibites Experiment Recording

## Setup - Infrastructure

I'm using Grafana Cloud and InfluxDB Cloud.
Grafana Cloud: https://grafana.com/products/cloud/
InfluxDB: https://www.influxdata.com/products/influxdb-cloud/

### InfluxDB
Sign up, make an account, make an org, and then make a bucket.  Also make a token granting access to the bucket or everything

### Grafana
Hook up InfluxDB as a data source in Grafana.  InfluxDB has docs that explain how to do this here: https://docs.influxdata.com/influxdb/cloud-serverless/process-data/visualize/grafana/ but the docs LIE TO YOU in a few places.  Use InfluxQL - don't worry about FlightSQL (unless you wanna struggle for an hour like I did trying to get it running).  Also use the `Flux` query language when you set up InfluxDB as a data source.  I didn't need to set a user or password.  I used the organization and set the default bucket to one that I created, then I made an API key granting full access, and put that in as a token.  Zip zop, baby.  If you run into problems, ask ChatGPT and/or google first please.

Also feel free to import the `basicdashboard.json` file as a dashboard into grafana.

![image](dashboard_example.png)

## Setup - Local

Use `pip` or `pip3` or `python3 -m pip` or whatever with the `-r requirements.txt` flag to install all the required packages.  Create a `config.json` file in the root of this dir with the following format:

    {
        "url": "[click the second from the top left word in the influxdb cloud page, then `settings` to see your cluster url]",
        "token": "[that token you made]",
        "org": "[top left word in the influxdb cloud page.  Influxdb calls it your account in some places on their UI.  Don't trust them]",
        "bucket": "[the bucket you made]",
        "autosavePath": "[path to where your game autosaves]"
    }

## Setup - Bibites

The values are stored in InfluxDB under `scenario` and `run` tags - the idea being that you'll run a Scenario `N` times, and then you can filter grafana graphs off of that.  IDK if this is the best way to do it - it's my first day using InfluxDB.

To set these values, your first zone in your scenario needs to be named in the format `"[Scenario] [Run #]"`.  If you don't do this, it _will break_.

This works by parsing data from autosaves, so I would recommend increasing your autosave frequency.

## Running it

Run `python ./src/main.py` or whatever the equivalent is for you