API reference
=============

Everything on this page is generated from the code, so it always matches
the installed version. The async client and the ``Async*`` domain APIs
mirror their sync counterparts method for method (a conformance test
enforces it), so the domain APIs are documented once, in their sync form.

Clients
-------

.. autoclass:: gpp_client.GPPClient
   :members:
   :inherited-members:

.. autoclass:: gpp_client.AsyncGPPClient
   :members:
   :inherited-members:

The UNSET sentinel
------------------

.. autoclass:: gpp_client.UnsetType

.. autodata:: gpp_client._base.UNSET

.. autofunction:: gpp_client.is_set

.. autoclass:: gpp_client._base.GPPModel

.. autoclass:: gpp_client._base.GPPInput
   :members: graphql_dump

Domain APIs
-----------

.. autoclass:: gpp_client.domains.ProgramAPI
   :members:
   :inherited-members:

.. autoclass:: gpp_client.domains.ObservationAPI
   :members:
   :inherited-members:

.. autoclass:: gpp_client.domains.TargetAPI
   :members:
   :inherited-members:

.. autoclass:: gpp_client.domains.AttachmentAPI
   :members:
   :inherited-members:

.. autoclass:: gpp_client.domains.CallForProposalsAPI
   :members:
   :inherited-members:

.. autoclass:: gpp_client.domains.GoatsAPI
   :members:
   :inherited-members:

.. autoclass:: gpp_client.domains.SchedulerAPI
   :members:
   :inherited-members:

.. autoclass:: gpp_client.domains.WorkflowStateAPI
   :members:
   :inherited-members:

Environments
------------

.. automodule:: gpp_client.environments
   :members:

Configuration
-------------

.. autoclass:: gpp_client.config.ResolvedConfig
   :members:

.. autofunction:: gpp_client.config.get_config_path

Errors
------

.. automodule:: gpp_client.errors
   :members:
   :show-inheritance:
