export default {
  title: "Robotaxi stats",
  root: "src",
  // One entry per page; group them (e.g. {name: "Safety", pages: [...]}) as more topics arrive.
  pages: [{name: "Waymo service areas", path: "/areas/waymo"}],
  pager: false,
  interpreters: {".py": ["python"]},
  footer:
    'Data and method: <a href="https://github.com/EwoutH/robotaxi_stats">github.com/EwoutH/robotaxi_stats</a>.'
};
