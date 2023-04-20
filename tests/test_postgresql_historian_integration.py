# -*- coding: utf-8 -*- {{{
# ===----------------------------------------------------------------------===
#
#                 Installable Component of Eclipse VOLTTRON
#
# ===----------------------------------------------------------------------===
#
# Copyright 2022 Battelle Memorial Institute
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy
# of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
# ===----------------------------------------------------------------------===
# }}}

import gevent
import pytest
from pathlib import Path
try:
    import psycopg2
    from psycopg2.sql import SQL, Identifier
except ImportError:
    pytest.skip(
        "Required imports for testing are not installed; Run pip install psycopg2-binary before running tests",
        allow_module_level=True,
    )

from historian.testing.integration_test_interface import HistorianTestInterface


class TestPostgresqlIntegration(HistorianTestInterface):

    @pytest.fixture(scope="module")
    def historian(self, volttron_instance):
        historian_config = {
            "connection": {
                "type": "postgresql",
                "params": {
                    'dbname': 'test_historian',
                    'port': 5432,
                    'host': 'localhost',
                    'user': 'postgres',
                    'password': 'postgres'
                }
            }
        }
        table_names = {
            "table_prefix": "",
            "data_table": "data",
            "topics_table": "topics",
            "meta_table": "meta"
        }

        historian_version = ">=4.0.0"
        self.setup_db(historian_config["connection"]["params"], table_names, historian_version)
        agent_path = Path(__file__).parents[1]
        historian_uuid = volttron_instance.install_agent(
            vip_identity='platform.historian',
            agent_dir=agent_path,
            config_file=historian_config,
            start=True)
        print("agent id: ", historian_uuid)
        gevent.sleep(1)
        yield "platform.historian", 6
        if volttron_instance.is_running() and volttron_instance.is_agent_running(historian_uuid):
            volttron_instance.stop_agent(historian_uuid)
        volttron_instance.remove_agent(historian_uuid)
        gevent.sleep(5)

    def setup_db(self, connection_params, table_names, historian_version):
        self.db_connection = psycopg2.connect(**connection_params)
        self.db_connection.autocommit = True
        try:
            self.cleanup_tables(table_names.values(), drop_tables=True)
        except Exception as exc:
            print('Error truncating existing tables: {}'.format(exc))
        if historian_version == "<4.0.0":
            # test for backward compatibility
            # explicitly create tables based on old schema - i.e separate topics and meta table - so that historian
            # does not create tables with new schema on startup
            print("Setting up for version <4.0.0")
            cursor = self.db_connection.cursor()
            cursor.execute(SQL(
                'CREATE TABLE IF NOT EXISTS {} ('
                'ts TIMESTAMP NOT NULL, '
                'topic_id INTEGER NOT NULL, '
                'value_string TEXT NOT NULL, '
                'UNIQUE (topic_id, ts)'
                ')').format(Identifier(table_names['data_table'])))
            cursor.execute(SQL(
                'CREATE INDEX IF NOT EXISTS {} ON {} (ts ASC)').format(
                Identifier('idx_' + table_names['data_table']),
                Identifier(table_names['data_table'])))
            cursor.execute(SQL(
                'CREATE TABLE IF NOT EXISTS {} ('
                'topic_id SERIAL PRIMARY KEY NOT NULL, '
                'topic_name VARCHAR(512) NOT NULL, '
                'UNIQUE (topic_name)'
                ')').format(Identifier(table_names['topics_table'])))
            cursor.execute(SQL(
                'CREATE TABLE IF NOT EXISTS {} ('
                'topic_id INTEGER PRIMARY KEY NOT NULL, '
                'metadata TEXT NOT NULL'
                ')').format(Identifier(table_names['meta_table'])))
            self.db_connection.commit()
            gevent.sleep(5)

    def cleanup_tables(self, truncate_tables, drop_tables=False):
        cursor = self.db_connection.cursor()
        if truncate_tables is None:
            truncate_tables = self.select_all_postgresql_tables()

        if drop_tables:
            for table in truncate_tables:
                if table:
                    cursor.execute(SQL('DROP TABLE IF EXISTS {}').format(
                        Identifier(table)))
        else:
            for table in truncate_tables:
                if table:
                    cursor.execute(psycopg2.SQL('TRUNCATE TABLE {}').format(
                        Identifier(table)))

        self.db_connection.commit()
        cursor.close()

    def select_all_postgresql_tables(self):
        cursor = self.db_connection.cursor()
        tables = []
        try:
            cursor.execute(f"""SELECT table_name FROM information_schema.tables
                                        WHERE table_catalog = 'test_historian' and table_schema = 'public'""")
            rows = cursor.fetchall()
            print(f"table names {rows}")
            tables = [columns[0] for columns in rows]
        except Exception as e:
            print("Error getting list of {}".format(e))
        finally:
            if cursor:
                cursor.close()
        return tables
