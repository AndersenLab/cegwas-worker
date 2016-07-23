import daemon
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
import requests
from daemonize import Daemonize
import logging

logging.basicConfig(format = "%(levelname)s\t%(message)s\t%(asctime)s")

# Set up file and stream loggers
fh = logging.FileHandler("/home/danielcook/cegwas-worker/poll.log", "w+")
fh.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.ERROR)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
ch.setFormatter(formatter)

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

log.addHandler(fh)
log.addHandler(ch)

pid = "/tmp/poll.pid"

ds = datastore.Client()

# Get instance information
metadata_server = "http://metadata/computeMetadata/v1/instance/"
metadata_flavor = {'Metadata-Flavor' : 'Google'}
gce_id = requests.get(metadata_server + 'id', headers = metadata_flavor).text
gce_name = requests.get(metadata_server + 'hostname', headers = metadata_flavor).text

def update_worker_state(status = "idle", report_slug = "", report_name = "", trait_slug = "", trait_name = "", release = 0):
    worker = datastore.Entity(key=ds.key("Worker", gce_id))
    worker["full_name"] = gce_name
    worker["release"] = release
    worker["last_update"] = unicode(datetime.now(pytz.timezone("America/Chicago")).isoformat())
    worker["last_update_unix"] = time.time()
    worker["status"] = unicode(status)
    worker["report_slug"] = unicode(report_slug)
    worker["report_name"] = unicode(report_name)
    worker["trait_slug"] = unicode(trait_slug)
    worker["trait_name"] = unicode(trait_name)
    ds.put(worker)


# Fetch queue
def get_queue():
    iron_credentials = ds.get(ds.key("credential", "iron"))
    return IronMQ(**dict(iron_credentials)).queue("cegwas-map")


def run_pipeline():
    log.info("starting_script")

    # Set initial worker status to idle.
    update_worker_state(status = "idle")

    # Fetch queue
    queue = get_queue()

    while True:
        resp = queue.reserve(timeout=3600, max = 1, wait = 3)["messages"]
        if len(resp) > 0:
            try:
                message = resp[0]

                # Acknowledge reciept of message
                args = message["body"]
                data = json.loads(args)
                report_slug = data["report_slug"]
                report_name = data["report_name"]
                trait_slug = data["trait_slug"]
                trait_name = data["trait_name"]
                release = data["release"]

                # Get db trait and report.
                report_item = report.get(report_slug = report_slug)
                trait_item = list(trait.select().filter(trait.trait_slug == trait_slug, trait.report == report_item).dicts().execute())[0]["id"]

                log.info("Starting Mapping: " + report_slug + "/" + trait_slug)
                # Refresh mysql connection
                db.close()
                db.connect()

                # Update status
                update_worker_state(status = "running", report_slug = report_slug, report_name = report_name, trait_slug = trait_slug, trait_name = trait_name, release = release)
                
                # Remove existing files if they exist
                [os.remove(x) for x in glob.glob("tables/*")]
                [os.remove(x) for x in glob.glob("figures/*")]

                # Run workflow
                comm = """Rscript run.R '{args}'""".format(args = args)

                print(comm)
                check_output(comm, shell = True)

                # Refresh mysql connection
                db.close()
                db.connect()

                update_worker_state(status = "running", report_slug = report_slug, report_name = report_name, trait_slug = trait_slug, trait_name = trait_name, release = release)
                
                # Upload results
                upload1 = """gsutil -m cp -r figures gs://cendr/{report_slug}/{trait_slug}/""".format(**locals())
                check_output(upload1, shell = True)
                upload2 = """gsutil -m cp -r tables gs://cendr/{report_slug}/{trait_slug}/""".format(**locals())
                check_output(upload2, shell = True)

                # Insert records into database

                # Remove existing
                mapping.delete().where(mapping.report == report_item, mapping.trait == trait_item).execute()

                if os.path.isfile("tables/processed_sig_mapping.tsv"):
                    with db.atomic():
                        with open("tables/processed_sig_mapping.tsv", 'rb') as tsvin:
                            tsvin = csv.DictReader(tsvin, delimiter = "\t")
                            marker_set = []
                            for row in tsvin:
                                if row["startPOS"] != "NA" and row["marker"] not in marker_set:
                                    marker_set.append(row["marker"])
                                    mapping(chrom = row["CHROM"],
                                            pos = row["POS"],
                                            report = report_item,
                                            trait = trait_item,
                                            variance_explained = row["var.exp"],
                                            log10p = row["log10p"],
                                            BF = row["BF"],
                                            interval_start = row["startPOS"],
                                            interval_end = row["endPOS"],
                                            version = "0.1",
                                            reference = "WS245").save()

                # Refresh mysql connection
                db.close()
                db.connect()

                # Insert Variant Correlation records into database.
                # Remove any existing
                mapping_correlation.delete().where(mapping_correlation.report == report_item, mapping_correlation.trait == trait_item).execute()

                try:
                    if os.path.isfile("tables/interval_variants_db.tsv"):
                        with db.atomic():
                            with open("tables/interval_variants_db.tsv") as tsvin:
                                tsvin = csv.DictReader(tsvin, delimiter = "\t")
                                for row in tsvin:
                                    mapping_correlation(report = report_item,
                                                        trait = trait_item,
                                                        CHROM = row["CHROM"],
                                                        POS = row["POS"],
                                                        gene_id = row["gene_id"],
                                                        alt_allele = row["num_alt_allele"],
                                                        num_strain = row["num_strains"],
                                                        correlation = row["corrected_spearman_cor"]).save()
                except:
                    pass

                # Update status of report submission
                trait.update(submission_complete=datetime.now(pytz.timezone("America/Chicago")), status="complete").where(trait.report == report_item, trait.trait_slug == trait_slug).execute()
                log.info("Finished " + report_slug + "/" + trait_slug)
            except Exception as e:
                log.exception("mapping errored")
                trait.update(submission_complete=datetime.now(pytz.timezone("America/Chicago")), status="error").where(trait.report == report_item, trait.trait_slug == trait_slug).execute()
                error = datastore.Entity(key=ds.key("Error", gce_id))
                error["machine_name"] = gce_name
                error["error"] = unicode(e)
                error["time"] = unicode(datetime.now(pytz.timezone("America/Chicago")).isoformat())
                error["report_slug"] = unicode(report_slug)
                error["trait_slug"] = unicode(trait_slug)
                ds.put(error)
            log.info("Deleting " + message['id'])
            queue.delete(message["id"], message["reservation_id"])
            update_worker_state(status = "idle")


# Run as a daemon
daemon = Daemonize(app="poll", 
                   pid=pid,
                   action=run_pipeline,
                   logger = log,
                   verbose=True,
                   foreground=True,
                   chdir="/home/danielcook/cegwas-worker",
                   keep_fds=[fh.stream.fileno()])
log.info("Starting")
daemon.start()


