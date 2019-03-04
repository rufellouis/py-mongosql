import unittest
from collections import OrderedDict

from mongosql.statements import *
from mongosql.exc import InvalidColumnError, InvalidQueryError, InvalidRelationError
from .models import *
from .util import stmt2sql


class StatementsTest(unittest.TestCase):
    """ Test individual statements """

    def test_projection(self):
        def test_by_full_projection(p, **expected_full_projection):
            """ Test:
                * get_full_projection()
                * __contains__() of a projection using its full projection
                * compile_columns()
            """
            self.assertEqual(p.get_full_projection(), expected_full_projection)

            # Test properties: __contains__()
            for name, include in expected_full_projection.items():
                self.assertEqual(name in p, True if include else False)

            # Test: compile_columns() only returns column properties
            columns = p.compile_columns()
            self.assertEqual(
                set(col.key for col in columns),
                set(col_name
                    for col_name in p.bags.columns.names
                    if expected_full_projection.get(col_name, 0))
            )

        # === Test: No input
        p = MongoProjection(Article).input(None)
        self.assertEqual(p.mode, p.MODE_EXCLUDE)
        self.assertEqual(p.projection, dict())

        # === Test: Valid projection, array
        p = MongoProjection(Article).input(['id', 'uid', 'title'])
        self.assertEqual(p.mode, p.MODE_INCLUDE)
        self.assertEqual(p.projection, dict(id=1, uid=1, title=1))

        test_by_full_projection(p,
                                # Explicitly included
                                id=1, uid=1, title=1,
                                # Implicitly excluded
                                theme=0, data=0,
                                # Properties excluded
                                calculated=0, hybrid=0,
                                )

        # === Test: Valid projection, dict, include mode
        p = MongoProjection(Article).input(dict(id=1, uid=1, title=1))
        self.assertEqual(p.mode, p.MODE_INCLUDE)
        self.assertEqual(p.projection, dict(id=1, uid=1, title=1))

        test_by_full_projection(p, # basically, the same thing
                                id=1, uid=1, title=1,
                                theme=0, data=0,
                                calculated=0, hybrid=0,
                                )

        # === Test: Valid projection, dict, exclude mode
        p = MongoProjection(Article).input(dict(theme=0, data=0))
        self.assertEqual(p.mode, p.MODE_EXCLUDE)
        self.assertEqual(p.projection, dict(theme=0, data=0))

        test_by_full_projection(p,
                                id=1, uid=1, title=1,
                                theme=0, data=0,
                                calculated=1, hybrid=1,
                                )

        # === Test: `default_exclude` in exclude mode
        p = MongoProjection(Article, default_exclude=('calculated', 'hybrid'))\
            .input(dict(theme=0, data=0))
        self.assertEqual(p.mode, p.MODE_EXCLUDE)
        self.assertEqual(p.projection, dict(theme=0, data=0,
                                            # Extra stuff
                                            calculated=0, hybrid=0))

        test_by_full_projection(p,
                                id=1, uid=1, title=1,
                                theme=0, data=0,
                                calculated=0, hybrid=0,  # now excluded
                                )

        # === Test: `default_exclude` in include mode (no effect)
        p = MongoProjection(Article, default_exclude=('calculated', 'hybrid')) \
            .input(dict(id=1, calculated=1))
        self.assertEqual(p.mode, p.MODE_INCLUDE)
        self.assertEqual(p.projection, dict(id=1, calculated=1))

        test_by_full_projection(p,
                                id=1, uid=0, title=0,
                                theme=0, data=0,
                                calculated=1, hybrid=0,  # one included, one excluded
                                )

        # === Test: default_projection
        pr = Reusable(MongoProjection(Article, default_projection=dict(id=1, title=1)))

        p = pr.input(None)
        self.assertEqual(p.mode, p.MODE_INCLUDE)
        self.assertEqual(p.projection, dict(id=1, title=1))

        p = pr.input(None)
        self.assertEqual(p.mode, p.MODE_INCLUDE)
        self.assertEqual(p.projection, dict(id=1, title=1))

        # === Test: force_include
        pr = Reusable(MongoProjection(Article, force_include=('id',)))

        # Include mode
        p = pr.input(dict(title=1))
        self.assertEqual(p.mode, p.MODE_INCLUDE)
        self.assertEqual(p.projection, dict(id=1, title=1))  # id force included
        # Exclude mode
        p = pr.input(dict(data=0))
        self.assertEqual(p.mode, p.MODE_MIXED)
        self.assertEqual(p.projection, dict(id=1,  # force included
                                            uid=1, title=1, theme=1,
                                            data=0,  # excluded by request
                                            calculated=1, hybrid=1))

        # === Test: force_exclude
        pr = Reusable(MongoProjection(Article, force_exclude=('data',)))
        # Include mode
        p = pr.input(dict(id=1))
        self.assertEqual(p.mode, p.MODE_INCLUDE)
        self.assertEqual(p.projection, dict(id=1))  # no `data`
        # Include mode: same property
        p = pr.input(dict(id=1, data=1))
        self.assertEqual(p.mode, p.MODE_INCLUDE)
        self.assertEqual(p.projection, dict(id=1))  # No more data, even though requested
        # Exclude mode
        p = pr.input(dict(theme=0))
        self.assertEqual(p.mode, p.MODE_EXCLUDE)
        self.assertEqual(p.projection, dict(theme=0,  # excluded by request
                                            data=0,  # force excluded
                                            ))

        # === Test: Invalid projection, dict, problem: invalid arguments passed to __init__()
        with self.assertRaises(InvalidColumnError):
            MongoProjection(Article, default_projection=dict(id=1, INVALID=1))
        with self.assertRaises(InvalidQueryError):
            MongoProjection(Article, default_projection=dict(id=1, title=0))

        with self.assertRaises(InvalidColumnError):
            MongoProjection(Article, default_exclude='id')
        with self.assertRaises(InvalidColumnError):
            MongoProjection(Article, default_exclude=('INVALID',))

        with self.assertRaises(InvalidColumnError):
            MongoProjection(Article, force_exclude='id')
        with self.assertRaises(InvalidColumnError):
            MongoProjection(Article, force_exclude=('INVALID',))

        with self.assertRaises(InvalidColumnError):
            MongoProjection(Article, force_include='id')
        with self.assertRaises(InvalidColumnError):
            MongoProjection(Article, force_include=('INVALID',))

        # === Test: Invalid projection, dict, problem: 1s and 0s
        pr = Reusable(MongoProjection(Article))

        with self.assertRaises(InvalidQueryError):
            pr.input(dict(id=1, title=0))

        # === Test: Invalid projection, dict, problem: invalid column
        with self.assertRaises(InvalidColumnError):
            pr.input(dict(INVALID=1))

        # === Test: A mixed object is only acceptable when it mentions EVERY column
        # No error
        MongoProjection(Article).input(dict(id=1, uid=1, title=1, theme=1, data=0,
                                            calculated=1, hybrid=1))

    def test_sort(self):
        sr = Reusable(MongoSort(Article))

        # === Test: no input
        s = sr.input(None)
        self.assertEqual(s.sort_spec, OrderedDict())

        # === Test: list
        s = sr.input(['id', 'uid+', 'title-'])
        self.assertEqual(s.sort_spec, OrderedDict([('id',+1),('uid',+1),('title',-1)]))

        # === Test: OrderedDict
        s = sr.input(OrderedDict([('id',+1),('uid',+1),('title',-1)]))
        self.assertEqual(s.sort_spec, OrderedDict([('id',+1),('uid',+1),('title',-1)]))

        # === Test: dict
        # One item allowed
        s = sr.input(dict(id=-1))
        # Two items disallowed
        with self.assertRaises(InvalidQueryError):
            s = sr.input(dict(id=-1, uid=+1))

        # === Test: invalid columns
        with self.assertRaises(InvalidColumnError):
            # Invalid column
            sr.input(dict(INVALID=+1))

        with self.assertRaises(InvalidColumnError):
            # Properties not supported
            sr.input(dict(calculated=+1))

        # Hybrid properties are ok
        sr.input(dict(hybrid=+1))

        # === Test: JSON column fields
        sr.input({'data.rating': -1})

    def test_group(self):
        # === Test: list
        g = MongoGroup(Article).input(['uid'])
        self.assertEqual(g.group_spec, OrderedDict(uid=+1))

    def test_filter(self):
        # === Test: empty
        f = MongoFilter(Article).input(None)  # no problem

        # === Test: simple key=value object
        f = MongoFilter(Article).input(OrderedDict([
            ('id', 1),
            ('hybrid', True),  # No error
            ('data.rating', 10),  # Accessing JSON column
        ]))
        self.assertEqual(len(f.expressions), 3)

        e = f.expressions[0]  # type e: FilterColumnExpression
        self.assertIsInstance(e, FilterColumnExpression)
        self.assertEqual(e.column_name, 'id')
        self.assertEqual(e.column.key, 'id')
        self.assertEqual(e.operator_str, '$eq')  # inserted
        self.assertEqual(e.value, 1)
        self.assertEqual(stmt2sql(e.compile_expression()), 'a.id = 1')

        e = f.expressions[1]  # type e: FilterColumnExpression
        self.assertEqual(e.column_name, 'hybrid')
        self.assertEqual(e.column.key, 'hybrid')
        self.assertEqual(e.operator_str, '$eq')  # inserted
        self.assertEqual(e.value, True)
        self.assertIn('(a.id > 10 AND (EXISTS (SELECT 1', stmt2sql(e.compile_expression()))

        e = f.expressions[2]  # type e: FilterColumnExpression
        self.assertIsInstance(e, FilterColumnExpression)
        self.assertEqual(e.column_name, 'data.rating')
        self.assertEqual(e.column.key, None)  # it's a JSON expressin
        self.assertEqual(e.real_column.key, 'data')
        self.assertEqual(e.operator_str, '$eq')  # inserted
        self.assertEqual(e.value, 10)
        self.assertEqual(stmt2sql(e.compile_expression()), "CAST((a.data #>> ['rating']) AS INTEGER) = 10")  # proper typecasting

        # === Test: scalar operators
        f = MongoFilter(ManyFieldsModel).input(OrderedDict([
            ('a', {'$lt': 100}),
            ('b', {'$lte': 100}),
            ('c', {'$ne': 100}),
            ('d', {'$gte': 100}),
            ('e', {'$gt': 100}),
            ('f', {'$in': [1, 2, 3]}),
            ('g', {'$nin': [1, 2, 3]}),
            ('h', {'$exists': 1}),
            ('i', {'$exists': 0}),
        ]))

        self.assertEqual(len(f.expressions), 9)

        e = f.expressions[0]
        self.assertEqual(e.operator_str, '$lt')
        self.assertEqual(stmt2sql(e.compile_expression()), 'm.a < 100')

        e = f.expressions[1]
        self.assertEqual(e.operator_str, '$lte')
        self.assertEqual(stmt2sql(e.compile_expression()), 'm.b <= 100')

        e = f.expressions[2]
        self.assertEqual(e.operator_str, '$ne')
        self.assertEqual(stmt2sql(e.compile_expression()), 'm.c != 100')

        e = f.expressions[3]
        self.assertEqual(e.operator_str, '$gte')
        self.assertEqual(stmt2sql(e.compile_expression()), 'm.d >= 100')

        e = f.expressions[4]
        self.assertEqual(e.operator_str, '$gt')
        self.assertEqual(stmt2sql(e.compile_expression()), 'm.e > 100')

        e = f.expressions[5]
        self.assertEqual(e.operator_str, '$in')
        self.assertEqual(stmt2sql(e.compile_expression()), 'm.f IN (1, 2, 3)')

        e = f.expressions[6]
        self.assertEqual(e.operator_str, '$nin')
        self.assertEqual(stmt2sql(e.compile_expression()), 'm.g NOT IN (1, 2, 3)')

        e = f.expressions[7]
        self.assertEqual(e.operator_str, '$exists')
        self.assertEqual(stmt2sql(e.compile_expression()), 'm.h IS NOT NULL')

        e = f.expressions[8]
        self.assertEqual(e.operator_str, '$exists')
        self.assertEqual(stmt2sql(e.compile_expression()), 'm.i IS NULL')

        # === Test: array operators
        f = MongoFilter(ManyFieldsModel).input(OrderedDict([
            ('aa', {'$eq': 1}),
            ('bb', {'$eq': [1, 2, 3]}),
            ('cc', {'$ne': 1}),
            ('dd', {'$ne': [1, 2, 3]}),
            ('ee', {'$in': [1, 2, 3]}),
            ('ff', {'$nin': [1, 2, 3]}),
            ('gg', {'$exists': 1}),
            ('hh', {'$exists': 0}),
            ('ii', {'$all': [1, 2, 3]}),
            ('jj', {'$size': 0}),
            ('kk', {'$size': 99}),
        ]))

        self.assertEqual(len(f.expressions), 11)

        e = f.expressions[0]
        self.assertEqual(e.operator_str, '$eq')
        self.assertEqual(stmt2sql(e.compile_expression()), '1 = ANY (m.aa)')

        e = f.expressions[1]
        self.assertEqual(e.operator_str, '$eq')
        self.assertEqual(stmt2sql(e.compile_expression()), 'm.bb = CAST(ARRAY[1, 2, 3] AS VARCHAR[])')

        e = f.expressions[2]
        self.assertEqual(e.operator_str, '$ne')
        self.assertEqual(stmt2sql(e.compile_expression()), '1 != ALL (m.cc)')

        e = f.expressions[3]
        self.assertEqual(e.operator_str, '$ne')
        self.assertEqual(stmt2sql(e.compile_expression()), 'm.dd != CAST(ARRAY[1, 2, 3] AS VARCHAR[])')

        e = f.expressions[4]
        self.assertEqual(e.operator_str, '$in')
        self.assertEqual(stmt2sql(e.compile_expression()), 'm.ee && CAST(ARRAY[1, 2, 3] AS VARCHAR[])')

        e = f.expressions[5]
        self.assertEqual(e.operator_str, '$nin')
        self.assertEqual(stmt2sql(e.compile_expression()), 'NOT m.ff && CAST(ARRAY[1, 2, 3] AS VARCHAR[])')

        e = f.expressions[6]
        self.assertEqual(e.operator_str, '$exists')
        self.assertEqual(stmt2sql(e.compile_expression()), 'm.gg IS NOT NULL')

        e = f.expressions[7]
        self.assertEqual(e.operator_str, '$exists')
        self.assertEqual(stmt2sql(e.compile_expression()), 'm.hh IS NULL')

        e = f.expressions[8]
        self.assertEqual(e.operator_str, '$all')
        self.assertEqual(stmt2sql(e.compile_expression()), 'm.ii @> CAST(ARRAY[1, 2, 3] AS VARCHAR[])')

        e = f.expressions[9]
        self.assertEqual(e.operator_str, '$size')
        self.assertEqual(stmt2sql(e.compile_expression()), 'array_length(m.jj, 1) IS NULL')

        e = f.expressions[10]
        self.assertEqual(e.operator_str, '$size')
        self.assertEqual(stmt2sql(e.compile_expression()), 'array_length(m.kk, 1) = 99')

        # === Test: operators on JSON columns
        f = MongoFilter(ManyFieldsModel).input(OrderedDict([
            ('j_a.rating', {'$lt': 100}),
            ('j_b.rating', {'$in': [1, 2, 3]}),
        ]))

        self.assertEqual(len(f.expressions), 2)

        e = f.expressions[0]
        self.assertEqual(e.operator_str, '$lt')
        self.assertEqual(stmt2sql(e.compile_expression()), "CAST((m.j_a #>> ['rating']) AS INTEGER) < 100")

        e = f.expressions[1]
        self.assertEqual(e.operator_str, '$in')
        self.assertEqual(stmt2sql(e.compile_expression()), "CAST((m.j_b #>> ['rating']) AS TEXT) IN (1, 2, 3)")

        # === Test: boolean expression
        f = MongoFilter(ManyFieldsModel).input({
            '$and': [
                OrderedDict([ ('a', 1), ('b', 2) ]),
                {'c': 3},
                {'g': {'$gt': 18}},
            ]
        })

        self.assertEqual(len(f.expressions), 1)

        e = f.expressions[0]
        self.assertIsInstance(e, FilterBooleanExpression)
        self.assertEqual(e.operator_str, '$and')

        self.assertIsInstance(e.value, list)
        self.assertIsInstance(e.value[0], list)
        self.assertEqual(stmt2sql(e.value[0][0].compile_expression()), 'm.a = 1')
        self.assertEqual(stmt2sql(e.value[0][1].compile_expression()), 'm.b = 2')
        self.assertIsInstance(e.value[1], list)
        self.assertEqual(stmt2sql(e.value[1][0].compile_expression()), 'm.c = 3')
        self.assertIsInstance(e.value[2], list)
        self.assertEqual(stmt2sql(e.value[2][0].compile_expression()), 'm.g > 18')
        self.assertEqual(stmt2sql(e.compile_expression()),
                         '((m.a = 1 AND m.b = 2) AND m.c = 3 AND m.g > 18)')

        f = MongoFilter(ManyFieldsModel).input({
            '$or': [
                {'a': 1},
                {'b': 1},
            ],
        })
        self.assertEqual(stmt2sql(f.compile_statement()),
                         '(m.a = 1 OR m.b = 1)')

        f = MongoFilter(ManyFieldsModel).input({
            '$nor': [
                {'a': 1},
                {'b': 1},
            ],
        })
        self.assertEqual(stmt2sql(f.compile_statement()),
                         'NOT (m.a = 1 OR m.b = 1)')

        f = MongoFilter(ManyFieldsModel).input({
            '$not': {
                'c': {'$gt': 18},
            }
        })
        self.assertEqual(stmt2sql(f.compile_statement()),
                         'm.c <= 18')  # wow, clever sqlalchemy!

        # === Test: nested boolean expression
        f = MongoFilter(ManyFieldsModel).input({
            '$not': OrderedDict([
                ('a', 1),
                ('$and', [
                    {'a': 1},
                    {'b': 1},
                    {'$or': [
                        {'a': {'$gt': 18}},
                        {'b': 1},
                    ]}
                ]),
            ])
        })
        self.assertEqual(stmt2sql(f.compile_statement()),
                         'NOT (m.a = 1 AND (m.a = 1 AND m.b = 1 AND (m.a > 18 OR m.b = 1)))')

        # === Test: related columns
        f = MongoFilter(Article).input(OrderedDict([
            # These two will be put together into a single subquery
            ('comments.id', 1),
            ('comments.uid', {'$gt': 18}),
            # These two will also be grouped
            ('user.id', 1),
            ('user.name', {'$nin': ['a', 'b']}),
        ]))

        self.assertEqual(len(f.expressions), 4)

        e = f.expressions[0]
        self.assertEqual(stmt2sql(e.compile_expression()), "c.id = 1")

        e = f.expressions[1]
        self.assertEqual(stmt2sql(e.compile_expression()), "c.uid > 18")

        e = f.expressions[2]
        self.assertEqual(stmt2sql(e.compile_expression()), "u.id = 1")

        e = f.expressions[3]
        self.assertEqual(stmt2sql(e.compile_expression()), "u.name NOT IN (a, b)")

        self.assertEqual(stmt2sql(f.compile_statement()),
                         # We rely on OrderedDict, so the order should be perfect
                         "((EXISTS (SELECT 1 \n"
                         "FROM a, c \n"
                         "WHERE a.id = c.aid AND c.id = 1 AND c.uid > 18)) AND "
                         "(EXISTS (SELECT 1 \n"
                         "FROM u, a \n"
                         "WHERE u.id = a.uid AND u.id = 1 AND u.name NOT IN (a, b))))")

        # === Test: Hybrid Properties
        f = MongoFilter(Article).input(dict(hybrid=1))
        self.assertIn('(a.id > 10 AND (EXISTS (SELECT 1 \nFROM u', stmt2sql(f.compile_statement()))
