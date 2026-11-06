export default {
  title: "Robotaxi stats",
  root: "src",
  style: "style.css",
  // Pages are listed on the landing page. Turn the sidebar on once there are a few.
  pages: [
    {name: "Waymo service areas", path: "/areas/waymo"},
    {name: "Tesla Robotaxi service areas", path: "/areas/tesla"}
  ],
  sidebar: false,
  pager: false,
  interpreters: {".py": ["python"]},
  footer:
    'Data and method: <a href="https://github.com/EwoutH/robotaxi_stats">github.com/EwoutH/robotaxi_stats</a>.'
};
