API reference
=============

Everything on this page is generated from the code, so it always matches
the installed version. The async client and the ``Async*`` domain APIs
mirror their sync counterparts method for method (a conformance test
enforces it), so the domain APIs are documented once, in their sync form.

Clients
-------

.. autoclass:: gpp_client2.GPPClient
   :members:
   :inherited-members:

.. autoclass:: gpp_client2.AsyncGPPClient
   :members:
   :inherited-members:

The UNSET sentinel
------------------

.. autoclass:: gpp_client2.UnsetType

.. autodata:: gpp_client2._base.UNSET

.. autofunction:: gpp_client2.is_set

.. autoclass:: gpp_client2._base.GPPModel

.. autoclass:: gpp_client2._base.GPPInput
   :members: graphql_dump

Domain APIs
-----------

.. autoclass:: gpp_client2.domains.ProgramAPI
   :members:
   :inherited-members:

.. autoclass:: gpp_client2.domains.ObservationAPI
   :members:
   :inherited-members:

.. autoclass:: gpp_client2.domains.TargetAPI
   :members:
   :inherited-members:

.. autoclass:: gpp_client2.domains.AttachmentAPI
   :members:
   :inherited-members:

.. autoclass:: gpp_client2.domains.CallForProposalsAPI
   :members:
   :inherited-members:

.. autoclass:: gpp_client2.domains.GoatsAPI
   :members:
   :inherited-members:

.. autoclass:: gpp_client2.domains.SchedulerAPI
   :members:
   :inherited-members:

.. autoclass:: gpp_client2.domains.WorkflowStateAPI
   :members:
   :inherited-members:

Environments
------------

.. automodule:: gpp_client2.environments
   :members:

Configuration
-------------

.. autoclass:: gpp_client2.config.ResolvedConfig
   :members:

.. autofunction:: gpp_client2.config.get_config_path

Errors
------

.. automodule:: gpp_client2.errors
   :members:
   :show-inheritance:
