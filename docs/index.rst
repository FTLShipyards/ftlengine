.. ftlengine documentation master file, created by
   sphinx-quickstart on Thu Oct  1 14:37:11 2020.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to ftlengine's documentation!
=====================================

.. toctree::
   :maxdepth: 2



Overview
========

The FTL engine is a command line tool for Docker based development and deployment

**WARNGING** this project is still under development



Installation
------------

First, install the CLI via Pip::

   pip install ftlengine


Quickstart
^^^^^^^^^^

The fastest way to get started with FTL is to chart an existing project::

   ftl chart add ~/path/to/.ftl

Then chose a project profile::

   ftl list-profiles
   ftl profile full

Finally, run the project::

   ftl jump




Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
