# Attachments

Metadata is GraphQL; file contents move over REST with presigned URLs,
and the client hides that split:

```python
attachment_id = gpp.attachments.upload(
    "p-123",
    attachment_type="SCIENCE",
    file_name="finder.pdf",
    file_path="~/finder.pdf",  # or content=b"..." for in-memory data
)
gpp.attachments.download_by_id(attachment_id, save_to="~/Downloads")
```

Downloads stream, so large files never load into memory. The presigned
download URL is served to you authenticated, but the URL itself is
fetchable without credentials until it expires - treat it accordingly.

The same methods are CLI commands: {doc}`../cli/attachments`.

## API

```{eval-rst}
.. autoclass:: gpp_client2.domains.AttachmentAPI
   :members:
   :inherited-members:
```
