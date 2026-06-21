"""Parse a Mixamo FBX (binary) and dump its bone hierarchy + rest pose transforms.
We need to confirm the skeleton matches Ariamodel.glb's J_Bip_* structure.
"""
from pathlib import Path
import struct

# Minimal FBX binary parser: walk the node tree and find skeleton nodes
class FBXReader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0
        # FBX header is 27 bytes; the file uses FBX 7.x binary format
        # Header: 'Kaydara FBX Binary  \\0' (23 bytes) + version (4 bytes)
        assert data[:23] == b'Kaydara FBX Binary  \x00', 'not a binary FBX'
        self.pos = 23
        self.version = struct.unpack('<I', data[23:27])[0]
        self.pos = 27
        # Skip top-level FBX header nodes (we want to get to 'Objects' section)
        self.objects = {}  # uid -> {'name': str, 'props': {...}, 'children': []}

    def read_uint32(self):
        v = struct.unpack('<I', self.data[self.pos:self.pos+4])[0]
        self.pos += 4
        return v

    def read_int32(self):
        v = struct.unpack('<i', self.data[self.pos:self.pos+4])[0]
        self.pos += 4
        return v

    def read_int64(self):
        v = struct.unpack('<q', self.data[self.pos:self.pos+8])[0]
        self.pos += 8
        return v

    def read_double(self):
        v = struct.unpack('<d', self.data[self.pos:self.pos+8])[0]
        self.pos += 8
        return v

    def read_float(self):
        v = struct.unpack('<f', self.data[self.pos:self.pos+4])[0]
        self.pos += 4
        return v

    def read_array(self, fbx_type: str, array_len: int):
        # Encoding: array_len, encoding (1=compressed), data
        encoding = self.read_uint32()
        comp_len = self.read_uint32()
        if encoding == 1:
            # compressed
            import zlib
            comp_data = self.data[self.pos:self.pos+comp_len]
            decomp = zlib.decompress(comp_data)
            self.pos += comp_len
        else:
            decomp = self.data[self.pos:self.pos+comp_len]
            self.pos += comp_len
        # Parse the decompressed data
        elem_size = {'d': 8, 'f': 4, 'l': 8, 'i': 4, 'c': 1}[fbx_type]
        count = array_len
        result = []
        for _ in range(count):
            if fbx_type == 'd':
                result.append(struct.unpack('<d', decomp[:8])[0])
                decomp = decomp[8:]
            elif fbx_type == 'f':
                result.append(struct.unpack('<f', decomp[:4])[0])
                decomp = decomp[4:]
        return result

    def read_property(self):
        fbx_type = self.data[self.pos:self.pos+1].decode('ascii')
        self.pos += 1
        if fbx_type == 'Y':  # int16
            v = struct.unpack('<h', self.data[self.pos:self.pos+2])[0]
            self.pos += 2
            return v
        elif fbx_type == 'C':  # bool
            v = struct.unpack('<b', self.data[self.pos:self.pos+1])[0]
            self.pos += 1
            return bool(v)
        elif fbx_type == 'I':  # int32
            v = self.read_int32()
            return v
        elif fbx_type == 'F':  # float
            v = self.read_float()
            return v
        elif fbx_type == 'D':  # double
            v = self.read_double()
            return v
        elif fbx_type == 'L':  # int64
            v = self.read_int64()
            return v
        elif fbx_type == 'S':  # string
            length = self.read_uint32()
            s = self.data[self.pos:self.pos+length].decode('utf-8')
            self.pos += length
            return s
        elif fbx_type == 'R':  # raw binary
            length = self.read_uint32()
            r = self.data[self.pos:self.pos+length]
            self.pos += length
            return r
        elif fbx_type in ('f', 'd', 'l', 'i'):  # array
            array_len = self.read_uint32()
            return self.read_array(fbx_type, array_len)
        else:
            raise ValueError(f'Unknown FBX property type: {fbx_type!r}')

    def read_node(self, end_pos=None):
        """Read one FBX node, return (name, props_dict, children_list)."""
        if end_pos is not None and self.pos >= end_pos:
            return None
        # Read end_offset (where this node ends) and num_props and prop_list_len and name_len and name
        end_offset = self.read_uint32()
        num_props = self.read_uint32()
        prop_list_len = self.read_uint32()
        name_len = self.read_uint32()
        name = self.data[self.pos:self.pos+name_len].decode('utf-8')
        self.pos += name_len

        # Read properties
        props_end = self.pos + prop_list_len
        props = []
        for _ in range(num_props):
            try:
                props.append(self.read_property())
            except Exception as e:
                # If we hit a complex type we don't handle, just store raw
                props.append(f'<unparseable: {e}>')
                break
        # Make sure we're at the right position after properties
        self.pos = props_end

        # Read children (nested nodes) until we reach end_offset
        children = []
        if self.pos < end_offset:
            # Read child nodes
            nested_end = end_offset
            while self.pos < nested_end:
                child = self.read_node(end_pos=nested_end)
                if child is None:
                    break
                children.append(child)

        self.pos = end_offset
        return (name, props, children)

    def parse(self):
        """Parse top-level FBX. Returns (objects_section, connections_section)."""
        # Top-level: FBXHeaderExtension, GlobalSettings, Documents, References, Definitions, Objects, Connections
        objects_section = None
        connections_section = None
        while self.pos < len(self.data):
            try:
                node = self.read_node(end_pos=len(self.data))
                if node is None:
                    break
                name, props, children = node
                if name == 'Objects':
                    objects_section = children
                elif name == 'Connections':
                    connections_section = children
            except Exception as e:
                break
        return objects_section, connections_section


def find_models(objects):
    """Return list of (uid, name, props) for Model objects (skeleton bones)."""
    models = []
    for obj in objects:
        if not obj: continue
        name, props, children = obj
        if name == 'Model':
            uid = props[0] if props else None
            # Look for 'Lcl Translation', 'Lcl Rotation', 'Lcl Scaling' in children
            model_name = None
            for child in children or []:
                if not child: continue
                cn, cp, cc = child
                if cn in ('Lcl Translation', 'Lcl Rotation', 'Lcl Scaling', 'Properties70'):
                    pass
            # Find name from connections
            models.append({'uid': uid, 'name': None, 'children': children, 'props': props})
    return models


def main():
    p = Path(r'C:\Users\Tench\Documents\AriaCompanion\ani\Idle.fbx')
    print(f'Reading {p.name} ({p.stat().st_size / 1024 / 1024:.2f} MB)...')
    data = p.read_bytes()
    reader = FBXReader(data)
    objects, connections = reader.parse()
    print(f'Objects: {len(objects) if objects else 0}')
    print(f'Connections: {len(connections) if connections else 0}')

    if not objects:
        print('Failed to parse')
        return

    # Find Model objects
    models = []
    for obj in objects:
        if not obj: continue
        name, props, children = obj
        if name == 'Model':
            uid = props[0] if props else None
            # Get the model name (it'll be in Properties70 under 'Lcl Translation' or via a 'Name' child)
            # Actually, model name is usually not in the Model object itself - it's looked up via Connections
            models.append({'uid': uid, 'children': children})

    # Build a map: child uid -> parent uid
    # Connections like: C "OO", child_uid, parent_uid (Object->Object)
    child_to_parent = {}
    uid_to_name = {}  # for NodeAttribute, Model, etc.
    for conn in connections or []:
        if not conn: continue
        name, props, children = conn
        if name == 'C' and len(props) >= 3 and props[0] == 'OO':
            child_uid, parent_uid = props[1], props[2]
            child_to_parent[child_uid] = parent_uid

    # Find names via the 'Name' connection type
    # 'C "OP", uid, property_name' style? Actually FBX connects object to its name via 'C "OO"'
    # The Model's name is typically via a separate "Name" property in Properties70

    # For Models, the name is the 1st property of type 'S' in Properties70 "Look" or "Name" attribute
    for m in models:
        for child in m['children']:
            if child and child[0] == 'Properties70':
                for p_node in (child[2] or []):
                    if p_node and p_node[1] and len(p_node[1]) > 0 and p_node[1][0] == 'Lcl Translation':
                        # P-node: name, type, sub_type, flags, payload
                        # props[0] = 'Lcl Translation', props[1] = 'Lcl Translation', props[2] = '', props[3] = '', props[4] = [x, y, z]
                        if len(p_node[1]) >= 5:
                            m['translation'] = p_node[1][4]
                        break

    # Find bone names via a different approach: search the connections for Model -> 'Name'
    # Actually, in FBX, the model name comes from the Name attribute in Properties70
    for m in models:
        for child in m['children']:
            if child and child[0] == 'Properties70':
                for p_node in (child[2] or []):
                    if p_node and len(p_node[1]) > 4 and p_node[1][0] == 'Name':
                        m['name'] = p_node[1][4]
                        break

    # Print skeleton
    print(f'\nFound {len(models)} Model objects')
    for m in models[:30]:
        name = m.get('name', m['uid'])
        trans = m.get('translation', '?')
        print(f'  uid={m["uid"]}  name={name!r}  pos={trans}')

    # Look for unique bone names
    unique_names = set()
    for m in models:
        if m.get('name'):
            unique_names.add(m['name'])
    print(f'\nUnique bone names ({len(unique_names)}):')
    for n in sorted(unique_names):
        if n and ('Hip' in n or 'Spine' in n or 'Shoulder' in n or 'Arm' in n or 'Leg' in n or 'Hand' in n or 'Foot' in n or 'Head' in n or 'Neck' in n or 'Toe' in n):
            print(f'  {n}')


if __name__ == '__main__':
    main()
