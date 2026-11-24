import { Routes, Route, Navigate } from "react-router";
import { AppShell } from "../shared/components/AppShell";
import { PublishingPage } from "../features/publishing/PublishingPage";
import { PostBankPage } from "../features/post-bank/PostBankPage";
import { ControlPlanePage } from "../features/control-plane/ControlPlanePage";
import { SourcesPage } from "../features/sources/SourcesPage";

import {ConnectionsPage} from "../features/publishing/ConnectionsPage";

export function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/connections" element={<ConnectionsPage />} />
        <Route path="/control" element={<ControlPlanePage />} />
        <Route path="/publishing" element={<PublishingPage />} />
        <Route path="/sources/library" element={<SourcesPage />} />
        <Route path="/production" element={<PostBankPage initialView="production" />} />
        <Route path="/bank" element={<PostBankPage initialView="review" />} />
        <Route path="/posts/workspace" element={<PostBankPage />} />
        <Route path="*" element={<Navigate to="/publishing" replace />} />
      </Routes>
    </AppShell>
  );
}
