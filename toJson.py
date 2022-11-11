#!/usr/bin/env python3

import sqlite3, json, sys, csv, traceback
import glob
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


    mil_long = []
    for file in glob.glob("./longnames/individual-types/*.csv"):
        with open(file, 'rt', encoding='utf-8-sig', errors='backslashreplace') as f:
            mil_long.extend(csv.reader(f, delimiter=',', quotechar='|'))

    with open(sys.argv[1], 'rt', encoding='utf-8', errors='backslashreplace') as jsonFile:
        text = jsonFile.read()
        with open('decodedJSON', 'wt', encoding='utf-8') as out:
            out.write(text)

    with open(sys.argv[1], 'rt', encoding='utf-8', errors='replace') as jsonFile:
        noblocks = json.load(jsonFile)

    types = {}

    if len(sys.argv) >= 4:
        with open(sys.argv[3], 'rt', encoding='utf-8', errors='replace') as jsonFile:
            newTypes = json.load(jsonFile)

    fixKey = {}
    delKey = []

    useLongName = set([ "ZZZZ","SHIP","BALL","GLID","ULAC","GYRO","UHEL","TWR","GND","PARA","DRON","EMER","SERV" ])

    for k,v in noblocks.items():
        v['f'] = v['f'] + '00'
        tc = v.get('t')
        if tc and tc not in useLongName:
            nT = newTypes.get(tc)
            if nT and nT[0]:
                v['d'] = nT[0]
                #print(v['d'])

        if k != k.upper():
            fixKey[k] = v

        if len(k) < 6 or len(k) > 6:
            delKey.append(k)

    for k,v in fixKey.items():
        del noblocks[k]
        noblocks[k.upper()] = v

    for k in delKey:
        del noblocks[k]
        print('ignoring bad addr: ' + str(k))

    if len(sys.argv) >= 5:
        with open(sys.argv[4], 'rt', encoding='utf-8', errors='replace_errors') as f:
            lines = f.readlines()
            for line in lines:
                try:
                    a = json.loads(line)
                except ValueError:
                    traceback.print_exc()
                    continue
                addr = a['icao'].upper()
                if len(addr) < 6 or len(addr) > 6:
                    print('ignoring bad addr: ' + str(addr))
                    continue
                e = noblocks.setdefault(addr, {})

                e.setdefault('f', '0000')

                f = e['f']
                ladd = a.get('faa_ladd')
                if ladd:
                    e['f'] = f[:3] + '1'

                mil = a.get('mil')
                if mil:
                    e['f'] = '1' + f[1:]

                ownop = a.get('ownop')
                if ownop:
                    e['ownop'] = ownop

                reg = a.get('reg')
                #if reg and not e.get('r'):
                if reg:
                    e['r'] = reg

                icaotype = a.get('icaotype')
                #if icaotype and not e.get('t'):
                # revert to this as soon as the E170 situation is fixed
                #if icaotype:
                if icaotype and (icaotype != 'E170' or not e.get('t')):
                    if e.get('t') and e.get('t') != icaotype:
                        nT = newTypes.get(icaotype)
                        if nT: e['d'] = nT[0]
                    e['t'] = icaotype

                year = a.get('year')
                if year:
                    e['year'] = year

                pia = a.get('faa_pia')
                if pia:
                    e = noblocks[addr] = {'f': '0010'}

    for k, v in noblocks.items():
        if 'f' in v and v['f'][2:] == '00':
            v['f'] = v['f'][:2]

    for row in mil_long:
        if len(row) < 5:
            print(row)
            continue

        icao = row[0]
        reg = row[1]
        tc = row[2]
        flags = row[3]
        longtype = row[4]

        entry = noblocks.get(icao)
        if entry and entry.get('t') == tc and entry.get('r') == reg:
            entry['d'] = longtype

    with open('aircraft.csv', 'w', newline='', encoding='utf-8') as csvfile:
        spamwriter = csv.writer(csvfile,
                delimiter=';', escapechar='\\',
                quoting=csv.QUOTE_NONE, quotechar=None,
                lineterminator='\n')
        for k,v in sorted(noblocks.items()): # readsb expects a trailing ; which is easily added with , None
            spamwriter.writerow([k, v.get('r'), v.get('t'), v.get('f'), v.get('d'), v.get('year'), v.get('ownop'), None ])

    regIcao = {}

    for k,v in sorted(noblocks.items()):
        # if the long type matches the one in newTypes, delete it as it doesn't need to be in this db
        # we still need it for the aircraft.csv, but that's already written out
        typeCode = v.get('t')
        typeLong = v.get('d')
        # disable this for now due to openadsb
        if False and typeCode and typeLong:
            nt = newTypes.get(v.get('t'))
            if nt and nt[0] == typeLong:
                #print(typeLong)
                del v['d']

        if "r" in v:
            regIcao[v["r"].replace("-", "")] = k

        bkey = k[0:1].upper()
        dkey = k[1:].upper()

        if v and bkey and dkey and bkey in blocks:
            blocks[bkey][dkey] = [ v.get('r'), v.get('t'), v.get('f'), v.get('d') ]
        else:
            print(k)
            print(bkey)
            print(dkey)
            print(v)

    with open((sys.argv[2] + '/regIcao.js'), 'w') as out:
        json.dump(obj=regIcao, fp=out, check_circular=False, separators=(',',':'), sort_keys=True)

    #with open('blocks.json', 'w') as out:
        #json.dump(blocks, out)

    writedb(blocks, sys.argv[2], 24576, False)
    sys.exit(0)
