import argparse
import xml.etree.ElementTree as ET
from typing import Optional
import re
from decimal import Decimal

SVG_NAMESPACE = '{http://www.w3.org/2000/svg}'
NAMESPACES = {
  'svg': 'http://www.w3.org/2000/svg',
}


if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='Flattens linearly-nested groups in a SVG file')
  parser.add_argument('input', type=str, help='Input SVG file.')
  parser.add_argument('output', type=str, help='Output SVG file name.')
  args = parser.parse_args()

  et = ET.parse(args.input)

  # Statistics
  trimmed_count = 0
  max_trim_depth = 0
  unmergeable_transforms = []

  # If this node is a group that is a linear tree (contains one non-group item and one nested group),
  # return the nested group. Otherwise, return None.
  def check_linear_tree(elt: ET.Element) -> Optional[ET.Element]:
    if elt.tag == f'{SVG_NAMESPACE}g' and len(elt) == 2:
      if elt[0].tag == f'{SVG_NAMESPACE}g' and elt[1].tag != f'{SVG_NAMESPACE}g':
        return elt[0]
      elif elt[0].tag != f'{SVG_NAMESPACE}g' and elt[1].tag == f'{SVG_NAMESPACE}g':
        return elt[1]
    return None  # default fallthrough

  # Currently, only translate supported - and this could be solved in a much more principled way
  translate_re = re.compile("^translate\((-?\d+(?:\.\d*)?)(?:[, ]\s*(-?\d+(?:\.\d*)?))?\)$")
  # Tries to merge two SVG transforms, merging the output (on success) and None (on failure)
  def merge_transform(parent: Optional[str], inner: Optional[str]) -> Optional[str]:
    if parent is None or inner is None:  # if either failed, propagate failure
      return None
    elif not parent:
      return inner
    elif not inner:
      return parent
    else:
      parentmatch = translate_re.match(parent)
      innermatch = translate_re.match(inner)

      if parentmatch and innermatch:
        newx = Decimal(parentmatch.groups()[0]) + Decimal(innermatch.groups()[0])
        if parentmatch.groups()[1] is not None:  # needed to handle implicit zero case
          parenty = Decimal(parentmatch.groups()[1])
        else:
          parenty = Decimal(0)
        if innermatch.groups()[1] is not None:
          innery = Decimal(innermatch.groups()[1])
        else:
          innery = Decimal(0)
        newy = parenty + innery

        return f"translate({newx},{newy})"
    return None  # default fallthrough

  # Looks for a two-nested linear tree structure (a group containing a non-group and a group, that inner group
  # also containing a non-group and group), tries to flatten it recursively (pulling out the inner group and
  # merging the transforms).
  def visit_node(elt: ET.Element, depth: int = 0) -> None:
    global trimmed_count, max_trim_depth, unmergeable_transforms

    outergroup = check_linear_tree(elt)
    outerdepth = 1
    while outergroup is not None:
      outer_transform = outergroup.attrib.get('transform', '')

      innergroup = check_linear_tree(outergroup)
      if innergroup is not None:
        inner_transform = innergroup.attrib.get('transform', '')
        merged_transform = merge_transform(outer_transform, inner_transform)
        if merged_transform is not None:
          outergroup.remove(innergroup)
          elt.append(innergroup)
          innergroup.attrib['transform'] = merged_transform

          outergroup = innergroup

          trimmed_count += 1
          max_trim_depth = max(max_trim_depth, depth + outerdepth)
          outerdepth += 1
        else:
          unmergeable_transforms.append((outer_transform, inner_transform))
          outergroup = None
      else:
        outergroup = None

    for child in elt.findall('svg:g', NAMESPACES):
      visit_node(child, depth + 1)

  visit_node(et.getroot())

  if unmergeable_transforms:
    print(f"Unmergeable transforms ({len(unmergeable_transforms)}): {unmergeable_transforms}")
  print(f"Trimmed {trimmed_count} nodes, max depth {max_trim_depth}")

  et.write(args.output)
