Input models
============

Every input model mutations and filters accept, generated from the merged
GPP schemas and rendered straight from the code. Inputs keep GraphQL's
omitted-versus-null semantics: a field you never set is not sent, a field
you set to ``None`` is sent as null (see :doc:`writing`).

.. automodule:: gpp_client2._generated.inputs
   :members:
   :undoc-members:

