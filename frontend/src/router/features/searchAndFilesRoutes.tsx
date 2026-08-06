import type { ReactElement } from "react";
import { Route } from "react-router-dom";

import {
  ArchiveSearchPage,
  FilesPage,
  SearchPage,
} from "@/router/pageRegistry";

export const searchAndFilesRoutes = (): ReactElement[] => [
  <Route key="/files" path="/files" element={<FilesPage />} />,
  <Route key="/archive" path="/archive" element={<ArchiveSearchPage />} />,
  <Route
    key="/archive/search"
    path="/archive/search"
    element={<ArchiveSearchPage />}
  />,
  <Route key="/search" path="/search" element={<SearchPage />} />,
];
