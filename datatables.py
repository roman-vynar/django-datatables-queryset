"""Server-side library to generate JSON data for JQuery DataTables from Django queryset.

Supports DataTables v1.10+ (no legacy support).

Apache License, Version 2.0
"""
import datetime
import re

from django.db.models import Q


class DataTablesQuerySetMixin(object):

    """Queryset mixin class to extend a single model queryset.

    Features:
        - global case-insensitive search by searchable columns;
        - multi-column sorting by orderable columns;
        - individual column filtering by searchable columns;
        - on individual column filtering the following rules apply depending of what a search value is:
            - started with '!' applies negated filtering, .exclude() instead of .filter();
            - 'None' string provided applies "__isnull=True" query;
            - integer provided applies "__exact" query for comparison (SQL "="),
            - comma presents, applies "__in" against the list obtained by splitting search value by comma;
            - otherwise, "__icontains" query applied (SQL "LIKE '%text%'");
        - matching UI column names to model fields including nested ones according to the mapping passed;
        - pagination support;
        - transforming datetimes into strings to be JSON-serializable;
        - when pagination is fully disabled, passing "limit" argument in URL will limit the number of rows returned;
        - DataTables acceptable response, ready for JSON dump;
        - no regex support.
    """

    def datatables(self, columns, request):
        """Process DataTable request and return JSON-serializable output for table rendering on frontend.

        Arguments:
            self        Django queryset.
            columns     Mapping of column names from DataTable header to model fields or callables.
            request     Django request containing GET parameters.


        # Example of usage
        class AnnouncementQuerySet(models.query.QuerySet, DataTablesQuerySetMixin):
            pass

        class AnnouncementManager(models.Manager):
            def get_queryset(self):
                return AnnouncementQuerySet(self.model, using=self._db)

        class Announcement(models.Model):
            ...
            objects = AnnouncementManager()

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


        request.GET example:
            _                           423754416929
            columns[0][data]	        "ID"
            columns[0][name]
            columns[0][orderable]	    true
            columns[0][search][regex]	false
            columns[0][search][value]
            columns[0][searchable]	    true
            columns[1][data]	        "Title"
            columns[1][name]
            columns[1][orderable]	    true
            columns[1][search][regex]	false
            columns[1][search][value]
            columns[1][searchable]	    true
            columns[2][data]	        "Created on"
            columns[2][name]
            columns[2][orderable]	    true
            columns[2][search][regex]	false
            columns[2][search][value]
            columns[2][searchable]	    true
            ...
            draw	                    4
            length	                    20
            order[0][column]	        0
            order[0][dir]	            asc
            order[1][column]	        2
            order[1][dir]	            desc
            search[regex]	            false
            search[value]
            start	                    0
            limit                       10  # Custom, optional
        """
        # All columns search and individual column filtering
        or_condition = Q()
        and_condition = dict()
        and_not_condition = dict()
        params = request.GET
        global_search_val = params.get('search[value]')
        for param, val in params.iteritems():
            # Check if searchable on UI
            col = re.search(r'^columns\[(.+)\]\[searchable\]$', param)
            if col and val == 'true':
                col = col.group(1)
                col_name = params.get('columns[%s][name]' % col)
                if not col_name:
                    col_name = params.get('columns[%s][data]' % col)

                model_field = columns.get(col_name)
                if not model_field or callable(model_field):
                    continue

                model_field = model_field.replace('.', '__')

                # Individual column filter args (logical AND, NOT)
                search_val = params.get('columns[%s][search][value]' % col)
                if search_val:
                    negated = False
                    if search_val.startswith('!'):
                        negated = True
                        search_val = search_val[1:]

                    if search_val == 'None':
                        method = 'isnull'
                        search_val = True
                    elif search_val.isdigit():
                        method = 'exact'
                    elif ',' in search_val:
                        search_val = search_val.split(',')
                        method = 'in'
                    else:
                        method = 'icontains'

                    if negated:
                        and_not_condition['%s__%s' % (model_field, method)] = search_val
                    else:
                        and_condition['%s__%s' % (model_field, method)] = search_val

                # Global search conditions (logical OR)
                elif global_search_val:
                    model_field = {'%s__icontains' % model_field: global_search_val}
                    or_condition |= Q(**model_field)

        # Multi-column sorting
        order_by = []
        for param, val in params.iteritems():
            # Match column order index
            idx = re.search(r'^order\[(.+)\]\[column\]$', param)
            if idx:
                idx = idx.group(1)
                col_dir = params.get('order[%s][dir]' % idx)
                # Validation
                try:
                    idx = int(idx)
                    assert col_dir in ['asc', 'desc']
                except (ValueError, TypeError, AssertionError):
                    continue

                # Check if orderable on UI
                if params.get('columns[%s][orderable]' % val) != 'true':
                    continue

                col_name = params.get('columns[%s][name]' % val)
                if not col_name:
                    col_name = params.get('columns[%s][data]' % val)

                model_field = columns.get(col_name)
                if not model_field or callable(model_field):
                    continue

                model_field = model_field.replace('.', '__')

                if col_dir == 'desc':
                    model_field = '-' + model_field

                order_by.insert(idx, model_field)

        # Pagination
        limit = 10
        offset = 0
        try:
            limit = int(params.get('length'))
            offset = int(params.get('start'))
            if limit == -1 and params.get('limit'):
                limit = int(params.get('limit'))
        except ValueError:
            pass

        # Queryset actions
        data = self.filter(**and_condition).exclude(**and_not_condition).filter(or_condition).order_by(*order_by)
        filtered_cnt = data.count()
        if limit > 0:
            data = data[offset: offset + limit]

        # Prepare output
        rows = []
        for item in data:
            row = dict()
            for attr, field in columns.iteritems():
                if callable(field):
                    val = field(item)
                else:
                    val = nested_getattr(item, field)

                # Transform datetime into string to be JSON-serializable
                if isinstance(val, datetime.datetime):
                    val = val.strftime('%Y-%m-%d %H:%M:%S')

                row[attr] = val
            rows.append(row)

        # Cast draw to an integer to prevent XSS
        try:
            draw = int(params.get('draw'))
        except (ValueError, TypeError):
            return {'draw': 0, 'data': [], 'recordsTotal': 0, 'recordsFiltered': 0}

        return {'draw': draw,
                'data': rows,
                'recordsTotal': self.count(),
                'recordsFiltered': filtered_cnt}


def nested_getattr(obj, attr):
    """getattr implementation supporting nested attributes."""
    attributes = attr.split('.')
    for i in attributes:
        if obj is None:
            break

        try:
            obj = getattr(obj, i)
        except AttributeError:
            raise

    return obj
