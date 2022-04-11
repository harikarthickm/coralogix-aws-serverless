import time
import boto3
import interfaces
from datetime import timezone, datetime


class Tester(interfaces.TesterInterface):
    def __init__(self):
        self.aws_dms_client = boto3.client('dms')
        self.cache = {}
        self.user_id = boto3.client('sts').get_caller_identity().get('UserId')
        self.account_arn = boto3.client('sts').get_caller_identity().get('Arn')
        self.account_id = boto3.client('sts').get_caller_identity().get('Account')
        self.all_dms_replica_instances = self._return_all_dms_replica_instances()

    def declare_tested_service(self) -> str:
        return 'dms'

    def declare_tested_provider(self) -> str:
        return 'aws'

    def run_tests(self) -> list:
        return self.detect_dms_certificate_is_not_expired() + \
               self.detect_dms_endpoint_should_use_ssl() + \
               self.detect_dms_replication_instance_should_not_be_publicly_accessible()

    def _append_dms_test_result(self, dms_data, test_name, issue_status):
        return {
            "user": self.user_id,
            "account_arn": self.account_arn,
            "account": self.account_id,
            "timestamp": time.time(),
            "item": dms_data['ReplicationInstanceIdentifier'],
            "item_type": "dms",
            "test_name": test_name,
            "test_result": issue_status
        }

    def _return_all_dms_replica_instances(self):
        replica_instances = []
        response = self.aws_dms_client.describe_replication_instances(MaxRecords=100)
        replica_instances.extend(response['ReplicationInstances'])
        while 'Marker' in response and response['Marker']:
            response = self.aws_dms_client.describe_replication_instances(MaxRecords=100, Marker=response['Marker'])
            replica_instances.extend(response['ReplicationInstances'])
        return replica_instances

    def _return_all_dms_certificates(self):
        dms_certificates = []
        response = self.aws_dms_client.describe_certificates(MaxRecords=100)
        dms_certificates.extend(response['Certificates'])
        while 'Marker' in response and response['Marker']:
            response = self.aws_dms_client.describe_certificates(MaxRecords=100, Marker=response['Marker'])
            dms_certificates.extend(response['Certificates'])
        return dms_certificates

    def _return_dms_certificate_status(self, test_name, issue_status):
        dms_certificate_status = []
        for dms_replica_instance_dict in self.all_dms_replica_instances:
            dms_certificate_status.append(
                self._append_dms_test_result(dms_replica_instance_dict, test_name, issue_status))
        return dms_certificate_status

    def detect_dms_endpoint_should_use_ssl(self):
        ssl_endpoint_result = []
        test_name = 'dms_endpoint_should_use_ssl'
        for dms_replica_instance_dict in self.all_dms_replica_instances:
            dms_connection_response = self.aws_dms_client.describe_connections(Filters=[
                {
                    'Name': 'replication-instance-arn',
                    'Values': [dms_replica_instance_dict['ReplicationInstanceArn']]
                },
            ])
            if dms_connection_response and 'Connections' in dms_connection_response and dms_connection_response[
                'Connections']:
                for dms_connection_response_dict in dms_connection_response:
                    dms_endpoint_response = self.aws_dms_client.describe_endpoints(Filters=[
                        {
                            'Name': 'endpoint-id',
                            'Values': [dms_connection_response_dict['EndpointIdentifier']]
                        },
                    ])
                    for dms_endpoint_response_dict in dms_endpoint_response['Endpoints']:
                        if 'SslMode' in dms_endpoint_response_dict and dms_endpoint_response_dict[
                            'SslMode'].lower() == 'none':
                            ssl_endpoint_result.append(
                                self._append_dms_test_result(dms_replica_instance_dict, test_name, 'issue_found'))
                        else:
                            ssl_endpoint_result.append(
                                self._append_dms_test_result(dms_replica_instance_dict, test_name, 'no_issue_found'))

        return ssl_endpoint_result

    def detect_dms_certificate_is_not_expired(self):
        dms_certificates = self._return_all_dms_certificates()
        issue_found = False
        test_name = 'dms_certificate_is_not_expired'
        if not dms_certificates:
            issue_found = True
        for dms_certificate_dict in dms_certificates:
            if datetime.now(timezone.utc) > dms_certificate_dict['ValidToDate']:
                issue_found = True
                break
        if issue_found:
            return self._return_dms_certificate_status(test_name, 'issue_found')
        else:
            return self._return_dms_certificate_status(test_name, 'no_issue_found')

    def detect_dms_replication_instance_should_not_be_publicly_accessible(self):
        dms_public_accessible = []
        test_name = 'dms_replication_instance_should_not_be_publicly_accessible'
        for dms_replica_instance_dict in self.all_dms_replica_instances:
            if dms_replica_instance_dict['PubliclyAccessible']:
                dms_public_accessible.append(
                    self._append_dms_test_result(dms_replica_instance_dict, test_name, 'issue_found'))
            else:
                dms_public_accessible.append(
                    self._append_dms_test_result(dms_replica_instance_dict, test_name, 'no_issue_found'))
        return dms_public_accessible

