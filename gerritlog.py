#!/usr/bin/env python3

import argparse
import colorama
import dataclasses
import enum
import git
import itertools
import netrc
import os
import re
import sys
import urllib
from gerrithelpers import GerritSSHClient


class VerifyStatus(enum.Enum):
    FAILURE = -1
    NO_SCORE = 0
    SUCCESS = 1


@dataclasses.dataclass
class LogOptions:
    max_count: int


class Commit:
    _chgid_regex = re.compile(r'Change-Id:\s+([a-zA-Z0-9]+)')

    def __init__(self, commit: git.Commit, gerrit):
        host, _, _ = get_origin(commit.repo)
        self._repo = commit.repo
        self._master = self._get_master()
        self._client = gerrit
        self.changeinfo = None
        self.commit = commit
        self.change_id = self._get_change_id()
        self.is_merged = self._check_merged()
        self.title = self._get_title()
        self.sha = self._get_sha()
        self.shortsha = self._get_shortsha()
        self.url = (f'{host}/r/{self.change_id}'
                    if self.change_id is not None else None)

    def _get_change_id(self):
        for line in [ln.strip() for ln in self.commit.message.split('\n')]:
            if match := self._chgid_regex.match(line):
                return match.groups(1)[0]
        return None

    def _get_master(self):
        for head in self._repo.heads:
            branch = head.tracking_branch()
            if branch is not None and branch.name == 'origin/master':
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
        if self.changeinfo is None:
            return VerifyStatus.NO_SCORE
        status = self.changeinfo.labels['Verified']
        if status.get('approved') is not None:
            return VerifyStatus.SUCCESS
        if status.get('rejected') is not None:
            return VerifyStatus.FAILURE
        return VerifyStatus.NO_SCORE

    def review_mark(self):
        if self.changeinfo is None:
            return 0
        review = self.changeinfo.labels['Code-Review']['all']
        marks = [*filter(lambda v: v != 0, [m['value'] for m in review])]
        return min(marks) if marks else 0

    def needs_rebase(self):
        if self.is_merged:
            return False
        if self.changeinfo is None:
            return False
        return self.changeinfo.status == 'MERGED'


def get_origin(repo: git.repo.base.Repo):
    origin = next(filter(lambda r: r.name == 'origin', repo.remotes), None)
    if origin is None:
        raise ValueError('Failed to find origin remote')
    for url in [urllib.parse.urlparse(u) for u in origin.urls]:
        if url.scheme == 'ssh':
            return url.hostname, url.username, url.port
    raise ValueError('Failed to find ssh origin remote')


def create_client(repo: git.repo.base.Repo):
    host, user, port = get_origin(repo)
    return GerritSSHClient(hostname=host, username=user, port=port)


def colorfmt(string: str, color: str, style: str = ''):
    return f'{color}{style}{string}{colorama.Style.RESET_ALL}'


def showlog(repo: git.repo.Repo, client: GerritSSHClient, options: LogOptions):
    color, style = colorama.Fore, colorama.Style
    statusmap = {VerifyStatus.FAILURE: colorfmt('x', color.RED),
                 VerifyStatus.NO_SCORE: colorfmt('?', color.YELLOW),
                 VerifyStatus.SUCCESS: colorfmt('v', color.GREEN)}
    markmap = {-2: colorfmt('-2', color.RED),
               -1: colorfmt('-1', color.RED),
               0: ' 0',
               1: colorfmt('+1', color.GREEN, style.DIM),
               2: colorfmt('+2', color.GREEN)}
    commits = []
    for i, c in enumerate(repo.iter_commits(), 1):
        commit = Commit(c, client)
        commits.append(commit)
        if commit.is_merged or i >= options.max_count:
            break
    infos = {
        info.id: info for info in
            client.changes.get([c.change_id for c in commits])}
    for commit in commits:
        commit.changeinfo = infos.get(commit.change_id)
        if commit.needs_rebase():
            status = '{}/{}'.format(colorfmt('rb', color.YELLOW),
                                    colorfmt('m', color.CYAN))
        elif commit.is_merged:
            status = colorfmt('   m', color.CYAN)
        else:
            status = '{}|{}'.format(markmap[commit.review_mark()],
                                    statusmap[commit.verify_status()])
        print('{} [{}] {}'.format(commit.shortsha, status, commit.title))


def showurl(repo: git.repo.Repo, client: GerritSSHClient, args: list[str]):
    commits = []
    for sha in args:
        if '..' in sha:
            crange = repo.merge_base(*sha.split('..'))
        else:
            crange = [sha]
        commits += [Commit(repo.commit(c), client) for c in crange]
    for commit in commits:
        print('{} {} {}'.format(commit.shortsha, commit.title, commit.url))


def main(args):
    colorama.init()
    repo = git.repo.Repo()
    client = create_client(repo)

    parser = argparse.ArgumentParser(description='Display information ' +
                                     'about a gerrit patch series.')
    subparsers = parser.add_subparsers()

    def _log(args):
        showlog(repo, client, LogOptions(max_count=int(args.max_count)))
    p = subparsers.add_parser('log', help='Show commit logs')
    p.add_argument('--max-count', help='Maximum number of commits to display', default=1 << 64)
    p.set_defaults(func=_log)

    def _link(args):
        showurl(repo, client, args.commit)
    p = subparsers.add_parser('link', help='Get a gerrit link for a given ' +
                                           'commit')
    p.add_argument('commit', help='Commit or a revision range to check',
                   nargs='+')
    p.set_defaults(func=_link)

    args = parser.parse_args(args)
    if not hasattr(args, 'func'):
        parser.print_help()
        exit(1)
    args.func(args)


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except (BrokenPipeError, KeyboardInterrupt):
        pass
