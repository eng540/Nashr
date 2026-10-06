import { Routes, Route, Navigate } from "react-router";
import { AppShell } from "../shared/components/AppShell";
import { PublishingPage } from "../features/publishing/PublishingPage";
import { PostBankPage } from "../features/post-bank/PostBankPage";

export function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/publishing" element={<PublishingPage />} />
        <Route path="/posts/workspace" element={<PostBankPage />} />
        <Route path="*" element={<Navigate to="/publishing" replace />} />
      </Routes>
    </AppShell>
  );
}
