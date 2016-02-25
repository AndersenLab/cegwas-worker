import httplib2
import base64
import json
from apiclient import discovery
from oauth2client import client as oauth2client
from subprocess import check_output
from iron_mq import *
from models import *
import datetime
from decimal import *
import time
from datetime import datetime
import pytz
import glob
import csv

from gcloud import datastore
ds = datastore.Client()

# Get instance information
import requests
metadata_server = "http://metadata/computeMetadata/v1/instance/"
metadata_flavor = {'Metadata-Flavor' : 'Google'}
gce_id = requests.get(metadata_server + 'id', headers = metadata_flavor).text
gce_name = requests.get(metadata_server + 'hostname', headers = metadata_flavor).text

def update_worker_state(status = "idle", report_slug = "", trait_slug = ""):
    worker = datastore.Entity(key=ds.key("Worker", gce_id))
    worker["full_name"] = gce_name
    worker["last_update"] = unicode(datetime.now(pytz.timezone("America/Chicago")).isoformat())
    worker["last_update_unix"] = time.time()
    worker["status"] = unicode(status)
    worker["report_slug"] = unicode(report_slug)
    worker["trait_slug"] = unicode(trait_slug)
    ds.put(worker)

update_worker_state()

# Fetch queue
queue = IronMQ().queue("cegwas-map")

while True:

    update_worker_state(status = "idle")
    resp = queue.reserve(timeout=3600, max = 1, wait = 3)["messages"]

    if len(resp) > 0:
        try:
            message = resp[0]

            # Acknowledge reciept of message
            args = message["body"]
            data = json.loads(args)
            report_slug = data["report_slug"]
            trait_slug = data["trait_slug"]

            # Refresh mysql connection
            db.close()
            db.connect()

            report_id = report.get(report_slug = report_slug).id

            # Update status
            update_worker_state(status = "running", report_slug = report_slug, trait_slug = trait_slug)
            
            # Remove existing files if they exist
            [os.remove(x) for x in glob.glob("tables/*")]
            [os.remove(x) for x in glob.glob("figures/*")]
            if os.path.isfile("report.html"):
                os.remove("report.html")

            # Run workflow
            comm = """Rscript -e "rmarkdown::render('report.Rmd')" '{args}'""".format(args = args)

            print(comm)
            check_output(comm, shell = True)

            # Refresh mysql connection
            db.close()
            db.connect()

            update_worker_state(status = "uploading_results", report_slug = report_slug, trait_slug = trait_slug)

            # Upload results
            upload1 = """gsutil -m cp report.html gs://cendr/{report_slug}/{trait_slug}/report.html""".format(**locals())
            check_output(upload1, shell = True)
            upload2 = """gsutil -m cp -r figures gs://cendr/{report_slug}/{trait_slug}/""".format(**locals())
            check_output(upload2, shell = True)
            upload3 = """gsutil -m cp -r tables gs://cendr/{report_slug}/{trait_slug}/""".format(**locals())
            check_output(upload3, shell = True)

            # Insert records into database
            if os.path.isfile("tables/processed_sig_mapping.tsv"):
                with open("tables/processed_sig_mapping.tsv", 'rb') as tsvin:
                    tsvin = csv.DictReader(tsvin, delimiter = "\t")
                    marker_set = []
                    for row in tsvin:
                        if row["startPOS"] != "NA" and row["marker"] not in marker_set:
                            marker_set.append(row["marker"])
                            mapping(chrom = row["CHROM"],
                                    pos = row["POS"],
                                    trait = trait.get(trait_slug = trait_slug),
                                    variance_explained = row["var.exp"],
                                    log10p = row["log10p"],
                                    BF = row["BF"],
                                    interval_start = row["startPOS"],
                                    interval_end = row["endPOS"],
                                    version = "0.1",
                                    reference = "WS245").save()

            # Update status of report submission
            trait.update(submission_complete=datetime.now(pytz.timezone("America/Chicago")), status="complete").where(trait.report == report_id, trait.trait_slug == trait_slug).execute()
            print("Finished " + report_slug + "/" + trait_slug)
        except:
            trait.update(submission_complete=datetime.now(pytz.timezone("America/Chicago")), status="error").where(trait.report == report_id, trait.trait_slug == trait_slug).execute()
        print "DELETING ITEM"
        queue.delete(message["id"], message["reservation_id"])

        


