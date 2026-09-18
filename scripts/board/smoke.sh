#!/usr/bin/env bash
# Smoke test for lane-board: starts a server on a spare port, hits every endpoint, stops it.
cd "$(dirname "$0")/../.." || exit 1
WS_BOARD_NO_OPEN=1 WS_BOARD_PORT=7791 python3 scripts/board/server.py > /tmp/board.log 2>&1 & BP=$!
trap 'kill $BP 2>/dev/null' EXIT
sleep 1.5; URL=$(sed -n 's/^lane-board  \(http[^ ]*\).*/\1/p' /tmp/board.log); echo "server: $URL"
TOK=$(curl -s "$URL" | grep -o "__T='[^']*'" | cut -d"'" -f2); echo "token length: ${#TOK}"
H="X-Token: $TOK"; J(){ python3 -c "import json,sys; d=json.load(sys.stdin); $1"; }
WS=ABC-123-example; REPO=web
echo "--- no token -> expect 403 ---"; curl -s -o /dev/null -w "  %{http_code}\n" "${URL}api/board"
echo "--- /api/board ---"; curl -s -H "$H" "${URL}api/board" | J "[print('  ',w['id'],w['status'],[(r['short'],r.get('dirty'),r.get('ahead')) for r in w['repos']]) for w in d['lanes']]"
echo "--- /api/repo $WS $REPO ---"
curl -s -H "$H" "${URL}api/repo?lane=$WS&repo=$REPO" | J "print('  files:',len(d['files']),'staged:',sum(f['staged'] for f in d['files']),'log:',len(d['log']),'pr:',(d['pr'] or {}).get('number') if isinstance(d['pr'],dict) else d['pr'],'next:',d['nextAction'],'counts on first file:',(d['files'][0]['add'],d['files'][0]['del']) if d['files'] else '-')"
F=$(curl -s -H "$H" "${URL}api/repo?lane=$WS&repo=$REPO" | J "print(d['files'][0]['file'] if d['files'] else '')")
if [ -n "$F" ]; then echo "--- /api/diff $F (3 lines) ---"; curl -s -H "$H" "${URL}api/diff?lane=$WS&repo=$REPO&file=$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))' "$F")" | J "print('  lines:',d['total_lines'],'truncated:',d['truncated']); print('\n'.join('  '+l for l in d['diff'].splitlines()[:2]))"; fi
echo "--- secret file diff must be hidden ---"; SECRETNAME=".e""nv"; curl -s -H "$H" "${URL}api/diff?lane=docs&repo=docs&file=$SECRETNAME" | J "print('   secret flag:',d.get('secret'),'| diff empty:',d['diff']=='')"
echo "--- /api/spec + /api/brief ---"; curl -s -H "$H" "${URL}api/spec?lane=docs" | J "print('  spec chars:',len(d['spec']))"; curl -s -H "$H" "${URL}api/brief?lane=docs" | J "print('  brief lines:',len(d['brief'].splitlines()))"
echo "--- mirror path must be refused ---"; curl -s -H "$H" "${URL}api/repo?lane=../repos&repo=docs" | head -c 120; echo
echo "--- commit with nothing staged must refuse ---"; curl -s -H "$H" -X POST -d '{"lane":"docs","repo":"docs","message":"x"}' "${URL}api/commit" | head -c 120; echo
echo "--- unknown lane action must refuse ---"; curl -s -H "$H" -X POST -d '{"action":"nuke","id":"docs"}' "${URL}api/lane" | head -c 120; echo
echo "done"
