import httplib2
import base64
import json
from apiclient import discovery
from oauth2client import client as oauth2client
from subprocess import check_output
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

def fetch_metadata(key):
    metadata_server = "http://metadata.google.internal/computeMetadata/v1/instance/attributes/"
    metadata_flavor = {'Metadata-Flavor' : 'Google'}
    return requests.get(metadata_server + key, headers = metadata_flavor).text

# Get instance information
gce_name = fetch_metadata('hostname')

def run_pipeline():
    log.info("starting_script")

    report_slug = fetch_metadata('report_slug')
    report_name = fetch_metadata('report_name')
    trait_slug = fetch_metadata('trait_slug')
    trait_name = fetch_metadata('trait_name')
    release = fetch_metadata('release')
    print report_slug, report_name, trait_slug, trait_name, release
    # Get db trait and report.
    report_item = report.get(report_name = report_name)
    trait_item = trait.get(trait.report == report_item, trait.trait_slug == trait_slug)

    log.info("Starting Mapping: " + report_slug + "/" + trait_slug)
    # Refresh mysql connection
    db.close()
    db.connect()

    # Remove existing files if they exist
    [os.remove(x) for x in glob.glob("tables/*")]
    [os.remove(x) for x in glob.glob("figures/*")]

    # Run workflow
    args = {'report_slug': report_slug, 'trait_slug': trait_slug}
    args = json.dumps(args)
    comm = """Rscript run.R '{args}'""".format(args = args)
    try:
        print(comm)
        check_output(comm, shell = True)

        # Refresh mysql connection
        db.close()
        db.connect()

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

run_pipeline()

