#!/usr/bin/env python3

import sqlite3, json, sys, csv
from contextlib import closing

def writedb(blocks, todir, blocklimit, debug):
    block_count = 0

    files = []

    sys.stderr.write('Writing blocks: ')

    queue = sorted(blocks.keys())
    while queue:
        bkey = queue[0]
        del queue[0]

        blockdata = blocks[bkey]
        if len(blockdata) > blocklimit:
            if debug: sys.stderr.write('Splitting block' + bkey + 'with' + len(blockdata) + 'entries..\n')

            # split all children out
            children = {}
            for dkey in blockdata.keys():
                new_bkey = bkey + dkey[0]
                new_dkey = dkey[1:]

                if new_bkey not in children: children[new_bkey] = {}
                children[new_bkey][new_dkey] = blockdata[dkey]

            # look for small children we can retain in the parent, to
            # reduce the total number of files needed. This reduces the
            # number of blocks needed from 150 to 61
            blockdata = {}
            children = sorted(children.items(), key=lambda x: len(x[1]))
            retained = 1

            while len(children[0][1]) + retained < blocklimit:
                # move this child back to the parent
                c_bkey, c_entries = children[0]
                for c_dkey, entry in c_entries.items():
                    blockdata[c_bkey[-1] + c_dkey] = entry
                    retained += 1
                del children[0]

            if debug: sys.stderr.write(len(children) + 'children created,' + len(blockdata) + 'entries retained in parent\n')
            children = sorted(children, key=lambda x: x[0])
            blockdata['children'] = [x[0] for x in children]
            blocks[bkey] = blockdata
            for c_bkey, c_entries in children:
                blocks[c_bkey] = c_entries
                queue.append(c_bkey)

        path = todir + '/' + bkey + '.js'
        files.append(bkey);
        if debug: sys.stderr.write('Writing' + len(blockdata) + 'entries to' + path + '\n')
        else:
            sys.stderr.write(bkey + ' ')
            sys.stderr.flush()
        block_count += 1
        with closing(open(path, 'w', encoding='utf-8')) as f:
            json.dump(obj=blockdata, fp=f, check_circular=False, separators=(',',':'), sort_keys=True)

    path = todir + '/files.js'
    with closing(open(path, 'w', encoding='utf-8')) as f:
        json.dump(obj=files, fp=f, check_circular=False, separators=(',',':'), sort_keys=True)
    sys.stderr.write('done.\n')
    sys.stderr.write('Wrote ' + str(block_count) + ' blocks\n')

if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.stderr.write('Reads the aircrafts.json like this one: https://github.com/Mictronics/readsb/blob/master/webapp/src/db/aircrafts.json with aircraft information and produces a directory of JSON files\n')
        sys.stderr.write('Syntax: ' + sys.argv[0] + ' <path to aircraft.json>  <path to DB dir>\n')
        sys.exit(1)

    blocks = {}

    for i in range(16):
        blocks['%01X' % i] = {}

    with open(sys.argv[1], 'rt', encoding='utf-8', errors='backslashreplace') as jsonFile:
        text = jsonFile.read()
        with open('decodedJSON', 'wt', encoding='utf-8') as out:
            out.write(text)

    with open(sys.argv[1], 'rt', encoding='utf-8', errors='replace_errors') as jsonFile:
        noblocks = json.load(jsonFile)

    types = {}

    if len(sys.argv) >= 4:
        with open(sys.argv[3], 'rt', encoding='utf-8', errors='replace_errors') as jsonFile:
             newTypes = json.load(jsonFile)

    short = {}
    for k,v in noblocks.items():
        if not v.get('d') and v.get('t'):
            nT = newTypes.get(v.get('t'))
            if nT:
                v['d'] = nT[0]
                #print(v['d'])

        if len(k) < 6:
            short[k] = v

    for k,v in short.items():
        del noblocks[k]
        noblocks[k.zfill(6)] = v

    with open('aircraft.csv', 'w', newline='', encoding='utf-8') as csvfile:
        spamwriter = csv.writer(csvfile,
                delimiter=';', escapechar='\\',
                quoting=csv.QUOTE_NONE, quotechar=None,
                lineterminator='\n')
        for k,v in sorted(noblocks.items()):
            spamwriter.writerow([k, v["r"], v["t"], v["f"], v["d"] ])

    regIcao = {}

    for k,v in sorted(noblocks.items()):
        bkey = k[0:1].upper()
        dkey = k[1:].upper()

        if "r" in v:
            regIcao[v["r"]] = k

        if v and bkey and dkey and bkey in blocks:
            blocks[bkey][dkey] = [ v["r"], v["t"], v["f"], v["d"] ]
        else:
            print(k)
            print(bkey)
            print(dkey)
            print(v)

    with open((sys.argv[2] + '/regIcao.js'), 'w') as out:
        json.dump(regIcao, out)

    #with open('blocks.json', 'w') as out:
        #json.dump(blocks, out)

    writedb(blocks, sys.argv[2], 24576, False)
    sys.exit(0)
