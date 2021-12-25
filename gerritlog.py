#!/usr/bin/env python3

import enum
import getpass
import git
import itertools
import netrc
import os
import re
import sys
import urllib


# Add the python-gerrit-api submodule to the path
sys.path.insert(0, '{}/python-gerrit-api'.format(
    os.path.dirname(os.path.realpath(__file__))))
import gerrit  # noqa


class VerifyStatus(enum.Enum):
    FAILURE = -1
    NO_SCORE = 0
    SUCCESS = 1


class Commit:
    _chgid_regex = re.compile(r'Change-Id:\s+([a-zA-Z0-9]+)')

    def __init__(self, commit: git.Commit, gerrit: gerrit.GerritClient):
        self._repo = commit.repo
        self._master = self._get_master()
        self._client = gerrit
        self.commit = commit
        self.change_id = self._get_change_id()
        self.is_merged = self._check_merged()
        self.title = self._get_title()
        self.sha = self._get_sha()
        self.shortsha = self._get_shortsha()

    def _get_change_id(self):
        for line in [ln.strip() for ln in self.commit.message.split('\n')]:
            if match := self._chgid_regex.match(line):
                return match.groups(1)[0]
        return None

    def _get_master(self):
        for head in self._repo.heads:
            if head.tracking_branch().name == 'origin/master':
                return head
        return None

    def _check_merged(self):
        head = self._master.tracking_branch().commit
        return (self.commit.hexsha in [c.hexsha for c in
                self._repo.merge_base(self.commit.hexsha, head.hexsha)])

    def _get_title(self):
        return self.commit.message.split('\n')[0]

    def _get_sha(self):
        return self.commit.hexsha

    def _get_shortsha(self):
        return self._repo.git.rev_parse(self._get_sha(), short=True)

    def verify_status(self):
        if self.change_id is None:
            return VerifyStatus.NO_SCORE
        patch = self._client.changes.get(self.change_id, detailed=True)
        status = patch.labels['Verified']
        if status.get('approved') is not None:
            return VerifyStatus.SUCCESS
        if status.get('rejected') is not None:
            return VerifyStatus.FAILURE
        return VerifyStatus.NO_SCORE


def get_url(repo: git.repo.base.Repo):
    origin = next(filter(lambda r: r.name == 'origin', repo.remotes), None)
    if origin is None:
        raise ValueError('Failed to find origin remote')
    for url in [urllib.parse.urlparse(u) for u in origin.urls]:
        if url.scheme in ('http', 'https'):
            return f'{url.scheme}://{url.netloc}'
    raise ValueError('Failed to find origin http(s) url')


def get_username():
    username = os.getenv('GERRIT_USERNAME')
    if username is not None:
        return username
    return getpass.getuser()


def create_client(repo: git.repo.base.Repo):
    url = get_url(repo)
    if url not in netrc.netrc().hosts:
        password = getpass.getpass()
    else:
        password = None
    return gerrit.GerritClient(base_url=url, username=get_username(),
                               use_netrc=password is None)


def main():
    repo = git.repo.Repo()
    client = create_client(repo)
    statusmap = {VerifyStatus.FAILURE: 'x',
                 VerifyStatus.NO_SCORE: '?',
                 VerifyStatus.SUCCESS: 'v'}
    for c in repo.iter_commits():
        commit = Commit(c, client)
        if commit.is_merged:
            status = 'm'
        else:
            status = statusmap[commit.verify_status()]
        print('{} [{}] {}'.format(commit.shortsha, status, commit.title))


if __name__ == '__main__':
    try:
        main()
    except (BrokenPipeError, KeyboardInterrupt):
        pass
