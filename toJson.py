#!/usr/bin/env python2

import sqlite3, json, sys, csv
from contextlib import closing

def writedb(blocks, todir, blocklimit, debug):
    block_count = 0

    print >>sys.stderr, 'Writing blocks:',

    queue = sorted(blocks.keys())
    while queue:
        bkey = queue[0]
        del queue[0]

        blockdata = blocks[bkey]
        if len(blockdata) > blocklimit:
            if debug: print >>sys.stderr, 'Splitting block', bkey, 'with', len(blockdata), 'entries..',

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

            if debug: print >>sys.stderr, len(children), 'children created,', len(blockdata), 'entries retained in parent'
            children = sorted(children, key=lambda x: x[0])
            blockdata['children'] = [x[0] for x in children]
            blocks[bkey] = blockdata
            for c_bkey, c_entries in children:
                blocks[c_bkey] = c_entries
                queue.append(c_bkey)

        path = todir + '/' + bkey + '.json'
        if debug: print >>sys.stderr, 'Writing', len(blockdata), 'entries to', path
        else: print >>sys.stderr, bkey,
        block_count += 1
        with closing(open(path, 'w')) as f:
            json.dump(obj=blockdata, fp=f, check_circular=False, separators=(',',':'), sort_keys=True)

    print >>sys.stderr, 'done.'
    print >>sys.stderr, 'Wrote', block_count, 'blocks'

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print >>sys.stderr, 'Reads the aircrafts.json like this one: https://github.com/Mictronics/readsb/blob/master/webapp/src/db/aircrafts.json with aircraft information and produces a directory of JSON files'
        print >>sys.stderr, 'Syntax: %s <path to aircraft.json>  <path to DB dir>' % sys.argv[0]
        sys.exit(1)

    blocks = {}

    for i in xrange(16):
        blocks['%01X' % i] = {}

    with open(sys.argv[1]) as jsonFile:
        noblocks = json.load(jsonFile)

    for k,v in noblocks.items():
        bkey = k[0:1].upper()
        dkey = k[1:].upper()

        blocks[bkey][dkey] = [ v["r"], v["t"], v["f"] ]


    #with open('blocks.json', 'w') as out:
        #json.dump(blocks, out)

    writedb(blocks, sys.argv[2], 24576, False)
    sys.exit(0)
