import json
import paramiko
from .commit import GerritCommit


class GerritSSHException(Exception):
    def __init__(self, message, exit_code, stderr):
        super().__init__(message)
        self.exit_code = exit_code
        self.stderr = stderr.read().decode('utf-8')

    def __str__(self):
        return 'GerritSSHException: {}\n{}'.format(
                self.exit_code, self.stderr)

class GerritSSHClient:
    class Changes:
        def __init__(self, client):
            self._client = client

        def get(self, id):
            return GerritCommit(id, json.loads(self._client.query(
                ['--all-approvals', f'change:{id}']).split('\n')[0]))

    def __init__(self, hostname, port=29418, username=None):
        self._client = paramiko.SSHClient()
        self._client.load_system_host_keys()
        self._client.connect(hostname, port=port, username=username)
        self.changes = GerritSSHClient.Changes(self)

    def _exec(self, cmd):
        stdin, stdout, stderr = self._client.exec_command(cmd)
        rc = stdout.channel.recv_exit_status()
        if rc != 0:
            raise GerritSSHException('Failed to execute command', rc, stderr)
        return stdout.read().decode('utf-8')

    def query(self, args: list[str]):
        return self._exec('gerrit query --format=json {}'.format(
                          ' '.join(args)))
