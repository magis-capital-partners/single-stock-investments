"""Lossless edits to a sealed author draft; no economic defaults or inference."""
import copy

from underwriting_contract import digest, require


SCHEMA = 'underwriting-contract-revision/1'


def materialize(base, proposal):
    require(isinstance(base, dict) and base.get('schema_version') == 'underwriting-contract/2',
            'A revision requires the complete prior economic contract')
    require(isinstance(proposal, dict) and proposal.get('schema_version') == SCHEMA and proposal.get('base_contract_hash') == digest(base),
            'Revision base contract hash changed')
    require(set(proposal) == {'schema_version', 'base_contract_hash', 'edits'}, 'Unknown revision envelope field')
    edits = proposal.get('edits')
    require(isinstance(edits, list) and 0 < len(edits) <= 1000, 'Revision needs bounded explicit edits')
    result = copy.deepcopy(base)

    def locate(rows, selector):
        match = {'id': selector} if isinstance(selector, str) else selector
        require(isinstance(match, dict) and match and all(isinstance(k, str) and
                isinstance(v, (str, int, float, bool)) for k, v in match.items()), 'Invalid revision selector')
        indices = [i for i, row in enumerate(rows) if isinstance(row, dict)
                   and all(row.get(k) == v for k, v in match.items())]
        require(len(indices) <= 1, 'Ambiguous revision selector: '+str(selector))
        return (indices[0] if indices else None), match

    for edit in edits:
        require(isinstance(edit, dict) and set(edit) <= {'path', 'op', 'value', 'before'}, 'Invalid revision edit object')
        path, op = edit.get('path'), edit.get('op', 'set')
        require(isinstance(path, list) and 0 < len(path) <= 64 and op in ('set', 'remove'), 'Invalid revision path or operation')
        require(('value' in edit) == (op == 'set'), 'Revision set needs a value; remove must not have one')
        parent = result
        for segment in path[:-1]:
            if isinstance(parent, dict):
                require(isinstance(segment, str) and segment in parent, 'Unknown revision parent: '+str(segment))
                parent = parent[segment]
            else:
                require(isinstance(parent, list), 'Revision parent must be an object or collection')
                index, _ = locate(parent, segment)
                require(index is not None, 'Unknown revision row: '+str(segment))
                parent = parent[index]
        key = path[-1]
        if isinstance(parent, dict):
            require(isinstance(key, str) and 'before' not in edit, 'Invalid object revision key')
            if op == 'remove':
                require(key in parent, 'Cannot remove an unknown revision field')
                del parent[key]
            else:
                parent[key] = copy.deepcopy(edit['value'])
        else:
            require(isinstance(parent, list), 'Revision target must be an object or collection')
            index, selector = locate(parent, key)
            if op == 'remove':
                require(index is not None and 'before' not in edit, 'Cannot remove an unknown revision row')
                parent.pop(index)
            else:
                value = edit['value']
                require(isinstance(value, dict) and all(value.get(k) == v for k, v in selector.items()),
                        'Revision row must preserve its selected identity')
                if index is not None:
                    require('before' not in edit, 'Replacement rows retain their existing order')
                    parent[index] = copy.deepcopy(value)
                else:
                    insertion = len(parent)
                    if 'before' in edit:
                        insertion, _ = locate(parent, edit['before'])
                        require(insertion is not None, 'Unknown insertion point in revision')
                    parent.insert(insertion, copy.deepcopy(value))
    require(result.get('schema_version') == 'underwriting-contract/2', 'Revision must retain the economic contract schema')
    return result


def validate_derivation(receipt, contract_hash):
    derivation = receipt.get('contract_revision')
    if derivation is None:
        return
    require(isinstance(derivation, dict) and isinstance(derivation.get('proposal'), dict)
            and isinstance(derivation.get('base_contract'), dict), 'Incomplete authored revision provenance')
    require(digest(derivation['proposal']) == derivation.get('provider_output_hash'), 'Authored revision output changed')
    materialized = materialize(derivation['base_contract'], derivation['proposal'])
    require(digest(materialized) == derivation.get('materialized_contract_hash') == contract_hash,
            'Authored revision does not derive the reviewed contract')
