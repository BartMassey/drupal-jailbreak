#!/usr/bin/python3
# Copyright (c) 2017 Bart Massey
# This work is available under the "MIT license".
# Please see the file COPYING in this distribution
# for license terms.

# Pull the content out of a Drupal site into
# portable formats.

# Top directory for generated website.
site_dir = "site"

# Directory where raw content is to be stored.
content_dir = "content"

# Directory where processed content is to be stored.
node_dir = "%s/node" % site_dir

import sys
import re
import os
import os.path as osp

import phpserialize
import MySQLdb
import MySQLdb.cursors

from filters.nl import filter_nl
from filters.autop import filter_autop
from filters.urlclean import filter_urlclean
from filters.url import filter_url
from filters.md import filter_md
from filters.txt import filter_txt
from filters.html import filter_html, filter_html_escape
from wrap_html import wrap_html
from make_logger import *

# Change to True for logging to stderr
main_log = make_logger("blog-rescue", False)

# Get the sitename from the command line.
assert len(sys.argv) == 2
sitename = sys.argv[1]

# Connect to the database using the information specified
# in the cnf file.
sitename_dashes = re.sub(r'\.', '-', sitename)
cwd = os.getcwd()
default_file = "%s/%s.my.cnf" % (cwd, sitename_dashes)
db = MySQLdb.connect(read_default_file=default_file)
c = db.cursor()

# Filters supported by this software.
supported_filters = {
    "filter.filter_html": (filter_html, None),
    "filter.filter_html_escape": (filter_html_escape, "txt"),
    "markdown.filter_markdown": (filter_md, "md"),
    "filter.filter_autop": (filter_autop, "autop."),
    "filter.filter_url": (filter_url, None),
    "php.php_code": (filter_txt, "php")
}

# Filter chains to run for filtering.
filters = dict()

# Filename extension to use for raw filter input.
suffixes = dict()

# Filter names
fnames = dict()

def register_filters():
    """Register the filter processing list for each filter
       format.
    """
    global supported_filters, filters, suffixes, fnames
    cf = db.cursor()
    cf.execute("""SELECT format, name FROM filter_format""")
    for fformat, ffname in cf:
        format_filters = []
        format_suffix = None
        c = db.cursor()
        c.execute("""SELECT module, name, settings FROM filter
                     WHERE format = %s AND status = 1
                     ORDER BY weight ASC""", (fformat,))
        for fm, fn, fs in c:
            fi = fm + "." + fn
            if fi in supported_filters:
                if supported_filters[fi]:
                    function, suffix = supported_filters[fi]
                    settings = phpserialize.loads(fs, decode_strings=True)
                    format_filters.append((fi, function, settings))
                    if not suffix:
                        continue
                    if suffix[-1] == '.':
                        if not format_suffix:
                            format_suffix = suffix
                        elif format_suffix[-1] == '.':
                            format_suffix += suffix
                        else:
                            parts = format_suffix.rsplit('.', 1)
                            if len(parts) == 1:
                                format_suffix = suffix + format_suffix
                            else:
                                assert len(parts) == 2
                                format_suffix = ("." + suffix).join(parts)
                    else:
                        if not format_suffix:
                            format_suffix = suffix
                        elif format_suffix[-1] != '.':
                            print("warning: extra filter %s ignored" % \
                                  (suffix,), file=sys.stderr)
                        else:
                            format_suffix += suffix
            else:
                print("warning: unknown filter %s ignored" % (fi,),
                      file=sys.stderr)
                supported_filters[fi] = None
        filters[fformat] = format_filters
        if not format_suffix:
            format_suffix = "html"
        elif format_suffix[-1] == '.':
            format_suffix += "html"
        suffixes[fformat] = format_suffix
        fnames[fformat] = ffname

# Register filters.
register_filters()

def run_filter_chain(content, fformat):
    """Run all the filters for the format in order with
       appropriate arguments.
    """
    assert fformat in filters
    for finame, function, settings in filters[fformat]:
        main_log("run", finame, settings)
        content = function(content, **settings)
    return content

# Empty or create the given directory.
def clean_dir(dir):
    if osp.isdir(dir):
        for fn in os.listdir(dir):
            os.remove(dir + "/" + fn)
    else:
        os.mkdir(dir)

# Clean the work directories.
clean_dir(content_dir)
clean_dir(node_dir)

# Extract node contents and store in files.
# XXX Captions are represented in field_data_body with
# body_format NULL when there is no caption body.
c.execute("""SELECT node.nid, node.title, field_data_body.body_value,
                    field_data_body.body_format
             FROM node JOIN field_data_body
             ON node.nid = field_data_body.entity_id
             WHERE field_data_body.body_format IS NOT NULL""")
index = ""
for nid, title, body, fformat in c:
    assert fformat in filters
    assert fformat in suffixes
    cfn = "%d.%s" % (nid, suffixes[fformat])
    nfn = "%d.html" % (nid,)
    body = filter_nl(body)
    with open("%s/%s" % (content_dir, cfn), "w") as content_file:
        content_file.write(body)
    main_log("filtering %s..." % (cfn,))
    body = run_filter_chain(body, fformat)
    body = filter_urlclean(body, sitename)
    wrapped = wrap_html(body, title=title)
    with open("%s/%s" % (node_dir, nfn), "w") as node_file:
        node_file.write(wrapped)
    main_log("... %s done" % (cfn,))
    index += '<li>[%s] <a href="/node/%s">%s</a></li>\n' % (nid, nfn, title)

# Generate an index file for the site.
title = "Archived Content: %s" % (sitename,)
index = "<ul>\n" + index + "</ul>\n"
index = wrap_html(index, title=title)
with open("%s/index.html" % (site_dir), "w") as index_file:
    index_file.write(index)
