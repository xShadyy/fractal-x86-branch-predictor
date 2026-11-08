#!/usr/bin/env python3
"""Static-only byte/provenance audit. Never loads or executes evidence binaries."""
import argparse
import hashlib
import json
import pathlib
import re
import runpy
import struct
import subprocess
import zipfile

ROOT = pathlib.Path('/workspace/scratch/b239a0078955')
REPO = ROOT / 'windows-followup-repo'
EVIDENCE = ROOT / 'k7-k8-review-20261108/evidence'
OUT = ROOT / 'k7-k8-review-20261108/static'
REV = '8080faed480a9eef086f1fc0396e38dba7de31c7'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pe_sections(image):
    start = struct.unpack_from('<I', image, 0x3c)[0]
    assert image[start:start+4] == b'PE\0\0'
    assert struct.unpack_from('<H', image, start+4)[0] == 0x8664
    count = struct.unpack_from('<H', image, start+6)[0]
    optional = start+24
    assert struct.unpack_from('<H', image, optional)[0] == 0x20b
    base = struct.unpack_from('<Q', image, optional+24)[0]
    table = optional+struct.unpack_from('<H', image, start+20)[0]
    result = []
    for i in range(count):
        at = table+40*i
        name = image[at:at+8].split(b'\0')[0].decode('ascii')
        size, rva, raw_size, raw_at = struct.unpack_from('<IIII', image, at+8)
        result.append(dict(name=name, va=base+rva, virtual_size=size,
                           data=image[raw_at:raw_at+raw_size]))
    return base, result


def dumpbin_rows(text):
    rows = []
    for line in text.splitlines():
        first = re.match(r'^\s+([0-9A-Fa-f]{16}): ((?:[0-9A-Fa-f]{2}(?: |$))+)(.*)', line)
        if first:
            rows.append(dict(address=int(first[1], 16), data=bytearray.fromhex(first[2]), asm=first[3].strip()))
        elif rows and re.fullmatch(r'\s{20}(?:[0-9A-Fa-f]{2} ?)+\s*', line):
            rows[-1]['data'].extend(bytes.fromhex(line.strip()))
    assert rows
    return rows


def fields(line):
    return dict(item.split('=', 1) for item in line.rstrip().split(',')[1:])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    build = json.loads((EVIDENCE/'build/build.json').read_text(encoding='utf-8-sig'))
    assert build['git_head'] == REV
    sources = []
    with zipfile.ZipFile(EVIDENCE/'sources.zip') as archive:
        names = sorted(archive.namelist())
        assert set(names) == set(build['source_sha256']) == set(build['source_sha256_lf'])
        for name in names:
            data = archive.read(name)
            trusted = subprocess.check_output(['git', 'show', f'{REV}:{name}'], cwd=REPO)
            assert sha(data) == build['source_sha256'][name]
            assert sha(data.replace(b'\r\n', b'\n')) == build['source_sha256_lf'][name]
            assert data == trusted, name
            sources.append(dict(path=name, sha256=sha(data), identical_to_trusted_revision=True))

    # Execute only the byte-contract module in the trusted local checkout.
    # It defines constants and code_for(), with no native execution.
    trusted_contract = subprocess.check_output(['git', 'show', f'{REV}:scripts/causal_receiver_contract.py'], cwd=REPO)
    assert trusted_contract == (REPO/'scripts/causal_receiver_contract.py').read_bytes()
    contract = runpy.run_path(str(REPO/'scripts/causal_receiver_contract.py'))
    template = contract['CODE']
    image = (EVIDENCE/'build/collector.exe').read_bytes()
    assert sha(image) == build['binary_sha256']
    image_base, sections = pe_sections(image)
    rows = dumpbin_rows((EVIDENCE/'build/collector.disasm.txt').read_text(encoding='utf-8-sig'))
    covered = set()
    bytes_verified = 0
    for row in rows:
        address, data = row['address'], row['data']
        section = next(s for s in sections if s['va'] <= address < s['va']+len(s['data']))
        offset = address-section['va']
        assert section['data'][offset:offset+len(data)] == data, hex(address)
        covered.update(range(address, address+len(data)))
        bytes_verified += len(data)
    text = next(s for s in sections if s['name'] == '.text')
    assert covered == set(range(text['va'], text['va']+text['virtual_size']))
    assert set(text['data'][text['virtual_size']:]) <= {0}
    occurrences = []
    for section in sections:
        at = section['data'].find(template)
        if at >= 0:
            occurrences.append(dict(section=section['name'], preferred_va=hex(section['va']+at)))
    assert occurrences == [dict(section='.rdata', preferred_va='0x14001c360')]

    # All addresses below refer to this exact PE's preferred image base.
    prepare = [r for r in rows if 0x140002740 <= r['address'] < 0x140002f5c]
    flush = [r for r in prepare if r['asm'].startswith('clflush')]
    assert len(flush) == 257
    target = lambda r: int(re.search(r'\[([0-9A-F]+)h\]', r['asm'])[1], 16)
    expected_targets = {base+4096*i for base in (0x14002c000, 0x14006c000, 0x1400ac000, 0x1400ec000) for i in range(64)}
    bank_flush = [r for r in flush if target(r) in expected_targets]
    assert len(bank_flush) == 256 and {target(r) for r in bank_flush} == expected_targets
    first, last = bank_flush[0]['address'], bank_flush[-1]['address']
    # The optimizer interleaves only the pending condition store into this region.
    straight = [r for r in prepare if first <= r['address'] <= last]
    nonflush = [r for r in straight if not r['asm'].startswith('clflush')]
    assert [(r['address'], bytes(r['data'])) for r in nonflush] == [(0x140002a2d, bytes.fromhex('44882dcc650200'))]
    assert target(flush[-1]) == 0x140029000
    address_rows = {r['address']:r for r in rows}
    assertions = {
        'token_zero_reset': (0x140002793, '40883566780200'),
        'token_one_reset': (0x14000278a, '4088356f880200'),
        'prelude_shared_call': (0x1400027ad, 'e8eef5ffff'),
        'prelude_limit_128': (0x1400027b6, '81ff80000000'),
        'train_shared_call': (0x1400027c9, 'e8d2f5ffff'),
        'train_limit_256': (0x1400027be, 'bf00010000'),
        'fresh_token_zero_store': (0x140002815, '8805e5770200'),
        'fresh_token_one_store': (0x140002824, '8805d6870200'),
        'post_training_condition_store': (0x140002a2d, '44882dcc650200'),
        'prepare_mfence': (0x140002f42, '0faef0'),
        'prepare_tail_jump_serialize': (0x140002f55, '48ff25fc90c600'),
        'branch_probe_prepare': (0x140002fc9, 'e872f7ffff'),
        'branch_probe_shared_call': (0x140002fce, 'e8cdedffff'),
        'shared_context_argument': (0x140001da4, '488d0d55a21200'),
        'shared_indirect_call': (0x140001dab, 'ff1597a2c600'),
        'cpl_compare_three': (0x140001db7, '83f903'),
        'branch_pc_offset_1402': (0x140001dca, '4881c27a050000'),
        'bind_bank_zero_before_code_install': (0x140001c89, '48890588a31200'),
        'bind_bank_one_before_code_install': (0x140001cbb, '4889055ea31200'),
        'code_copy_length_1743': (0x140001ce5, '41b8cf060000'),
        'verify_rx_code_length_1743': (0x140001d3c, '41b8cf060000'),
    }
    code_checks = []
    for name, (at, expected) in assertions.items():
        row = address_rows[at]
        assert bytes(row['data']) == bytes.fromhex(expected), name
        code_checks.append(dict(check=name, preferred_va=hex(at), bytes=expected, instruction=row['asm'], passed=True))

    attempts = []
    total_samples = 0
    for folder in sorted(EVIDENCE.glob('attempt-*')):
        if not folder.is_dir():
            continue
        metadata = {}
        snapshots = {}
        bindings = {}
        sample_count = 0
        aux_values = set()
        with (folder/'trace.log').open() as stream:
            for line in stream:
                if line.startswith('K7_RUN,'):
                    metadata = fields(line)
                elif line.startswith('K7_CPU,'):
                    cpu = fields(line)
                elif line.startswith('K7_CODE,'):
                    values = fields(line)
                    snapshots[values['mode']] = bytes.fromhex(values['hex'])
                elif line.startswith('K7_BIND,'):
                    values = fields(line)
                    bindings[values['mode']] = (int(values['bank0_addr'], 16), int(values['bank1_addr'], 16))
                elif line.startswith('K7_SAMPLE,'):
                    parts = line.rstrip().split(',')
                    assert len(parts) == 24
                    assert int(parts[16]) == 3
                    assert int(parts[18], 16) == int(metadata['code_addr'], 16)+contract['BRANCH']
                    kind = parts[5]
                    omitted = kind.startswith(('no_probe_', 'hot_', 'cold_'))
                    assert int(parts[17]) == (255 if omitted else 3)
                    assert int(parts[19], 16) == (0 if omitted else int(metadata['code_addr'], 16)+contract['BRANCH'])
                    aux = [int(v) for v in parts[20:24]]
                    assert aux[0] == aux[1] and aux[2] == aux[3]
                    aux_values.update(aux)
                    sample_count += 1
        assert sample_count == 512*5*16*4
        study = metadata['study']
        assert set(snapshots) == set(bindings) == set(contract['MODES'][study])
        mode_checks = []
        for mode, trace_bytes in snapshots.items():
            snapshot = (folder/f'runtime.{mode}.bin').read_bytes()
            expected = contract['code_for'](study, mode)
            assert snapshot == trace_bytes == expected
            private = study == 'receiver' and mode == 'sink_both'
            expected_binding = tuple(int(metadata[f'{"sink" if private else "bank"}{n}_addr'], 16) for n in range(2))
            assert bindings[mode] == expected_binding
            mode_checks.append(dict(mode=mode, sha256=sha(snapshot), length=len(snapshot),
                                    contract_and_trace_identical=True, recorded_binding_correct=True))
        # Confirm runtime image offsets against static PE object positions under ASLR.
        load_base = int(metadata['condition_addr'], 16)-0x29000
        for key, offset in [('token0_addr', 0x2a000), ('token1_addr', 0x2b000), ('bank0_addr', 0x2c000),
                            ('bank1_addr', 0x6c000), ('sink0_addr', 0xac000), ('sink1_addr', 0xec000)]:
            assert int(metadata[key], 16) == load_base+offset
        attempts.append(dict(attempt=folder.name, study=study, modes=mode_checks,
                             runtime_metadata_matches_pe_static_offsets=True,
                             sample_count=sample_count, all_recorded_cpl_pc_checks_passed=True,
                             intra_reload_aux_matches=True, observed_aux_values=sorted(aux_values),
                             reported_hypervisor=int(cpu['hypervisor']),
                             reported_lfence_always_serializing=int(cpu['lfence_always_serializing'])))
        total_samples += sample_count

    result = dict(
        schema=1, scope='Static source, PE, disassembly and recorded-code provenance review; evidence executables were never executed',
        trusted_git_revision=REV, evidence_binary_sha256=sha(image), evidence_binary_matches_manifest=True,
        sources=sources,
        pe=dict(preferred_image_base=hex(image_base), machine='AMD64', optional_header='PE32+',
                instruction_rows=len(rows), bytes_verified=bytes_verified,
                all_recorded_dumpbin_rows_match_pe_bytes=True, all_virtual_text_bytes_covered=True,
                omitted_raw_alignment_padding_bytes=len(text['data'])-text['virtual_size'],
                omitted_raw_alignment_padding_all_zero=True,
                text_raw_size=len(text['data']), text_virtual_size=text['virtual_size'], text_sha256=sha(text['data']),
                embedded_template_sha256=sha(template), embedded_template_occurrences=occurrences),
        prepare_flush=dict(bank_instructions=256, distinct_bank_targets=256, all_four_banks_all_64_pages=True,
                           bank_range_has_no_branch_or_call=True, condition_store_interleaved_at='0x140002a2d',
                           conditional_condition_flush_at='0x140002f3b', mfence_at='0x140002f42',
                           serializing_helper_tail_jump_at='0x140002f55'),
        emitted_code_checks=code_checks, attempts=attempts, total_recorded_samples_checked=total_samples,
        findings=[
            'No material static implementation defect found in the reviewed preparation, shared-site, timer or patch paths.',
            'MSVC preserves all 256 distinct public/sink CLFLUSH operations without loop branches; it schedules the probe-condition store inside that region, before the final condition flush and MFENCE.',
            'Fresh page tags are stored after both training loops. Training uses page zero; probe tags are from pages 1 through 63 in the trusted schedule.',
            'The branch probe calls preparation and then the same invoke_shared wrapper. The wrapper calls one runtime site using one context and validates recorded CPL and branch PC.',
            'Both dependency-mask controls retain TEST/CMOV topology; true masks consume the resolved condition register, sham masks consume fixed zero/one constants.',
            'Receiver ablation replaces a five-byte marker load with a five-byte constant return. sink_both preserves instruction bytes and binds private banks before training.',
            'Runtime site saves and restores Windows nonvolatile RBX/RSI/RDI. Timer, serial and hot helpers preserve RBX across CPUID; other touched general registers are volatile in the x64 ABI.',
            'Reload uses CPUID before timing, RDTSCP then LFENCE before the measured load, and RDTSCP then LFENCE afterward. Both AUX values are stored after the timed load through an R9 pointer that survives CPUID and RDTSCP.'
        ],
        material_limits=[
            'Static review validates code bytes and the declared apparatus, not which instructions executed speculatively or the physical cause of cache timings.',
            'Runtime snapshots are recorded during initial installation. The program reinstalls and memcmp-checks expected bytes per mode block, but there is no externally attested instruction trace of every episode.',
            'Source hashes and embedded-template agreement are not a reproducible MSVC build proof or proof of compiler/tool provenance; the supplied build manifest is a record, not an independent compiler attestation.',
            'Every trace reports a hypervisor. The guest-visible LFENCE-always-serializing bit is zero, so an LFENCE mode cannot be described as a validated serializing barrier on this configuration from that bit alone.',
            'All recorded TSC_AUX values are zero. Equality detects no reported migration, but the hypervisor may supply a nonunique or fixed AUX value; affinity and AUX equality do not independently attest physical-core residency.',
            'All six attempts are user-mode on one host. This review cannot establish cross-privilege influence, kernel leakage, Apple behavior, or independent-boot replication.'
        ],
        native_execution_performed=False, new_processor_measurements=0, passed=True)
    (OUT/'static-code-review.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(passed=True, sources=len(sources), pe_rows=len(rows), bytes_verified=bytes_verified,
                          attempts=len(attempts), snapshots=sum(len(x['modes']) for x in attempts), samples=total_samples)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=pathlib.Path, default=REPO)
    parser.add_argument('--evidence', type=pathlib.Path, default=EVIDENCE)
    parser.add_argument('--output', type=pathlib.Path, default=OUT)
    args = parser.parse_args()
    REPO=args.repo.resolve(); EVIDENCE=args.evidence.resolve(); OUT=args.output.resolve()
    main()
