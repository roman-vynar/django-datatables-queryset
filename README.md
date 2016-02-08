# Django DataTablesQuerySetMixin

Server-side library to generate JSON data for JQuery DataTables from Django queryset result.
Comes as Queryset mixin class to extend a single model queryset.
Supports DataTables v1.10+ (no legacy support).

## Features

* global case-insensitive search by searchable columns;
* multi-column sorting by orderable columns;
* individual column filtering by searchable columns;
* on individual column filtering the following rules apply depending of what a search value is:
    * started with '!' applies negated filtering, .exclude() instead of .filter();
    * 'None' string provided applies "__isnull=True" query;
    * integer provided applies "__exact" query for comparison (SQL "="),
    * comma presents, applies "__in" against the list obtained by splitting search value by comma;
    * otherwise, "__icontains" query applied (SQL "LIKE '%text%'");
* matching UI column names to model fields including nested ones according to the mapping passed;
* pagination support;
* transforming datetimes into strings to be JSON-serializable;
* when pagination is fully disabled, passing "limit" argument in URL will limit the number of rows returned;
* DataTables acceptable response, ready for JSON dump;
* no regex support.

## Example of usage

Here is some excerpts of code.

models.py:
```
class AnnouncementQuerySet(models.query.QuerySet, DataTablesQuerySetMixin):
    pass

class AnnouncementManager(models.Manager):
    def get_queryset(self):
        return AnnouncementQuerySet(self.model, using=self._db)

class Announcement(models.Model):
    id = models.AutoField(primary_key=True)
    ...
    objects = AnnouncementManager()
```

views.py:
```
# DataTable header mapping
columns = {
    'ID': 'id',
    'Title': 'title',
    'Created on': 'created',
    'Created by': 'user.name',
    'Acknowledged': lambda a: a.acks.filter(created__isnull=False).count()
}
data = Announcement.objects.all()
data = data.datatables(columns, request)

return JsonResponse(data)
```

announcements.html:
```
<table id="my_datatable" class="display compact">
    <thead>
        <tr>
            <th>ID</th>
            <th>Title</th>
            <th>Created on</th>
            <th>Created by</th>
            <th>Acknowledged</th>
        </tr>
    </thead>
</table>

<script type="text/javascript">
    $(document).ready(function() {
        var table_options = {
            "processing": true,
            "serverSide": true,
            "ajax": "{% url 'my.appy' %}?json=true",
            "paging": true,
            "ordering": true,
            "searching": true,
            "info": true,
            "order": [[1, "desc"]],
            "pageLength": 20,
            "lengthChange": false,
            "columns": [
                {"data": "ID"},
                {"data": "Title"},
                {"data": "Created on",},
                {"data": "Created by"},
                {"data": "Acknowledged"}
            ]
        };
        var oTable = $("#my_datatable").DataTable(table_options);
    });
</script>
```

