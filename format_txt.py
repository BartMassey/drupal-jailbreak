#!/usr/bin/python3
# Copyright (c) 2017 Bart Massey
# This work is available under the "MIT license".
# Please see the file COPYING in this distribution
# for license terms.

# "Format" text content.

# Return a protected version of
# the given text content.
def format_txt(content, sitename, title):
    return "<pre>\n" + content + "\n</pre>\n"
