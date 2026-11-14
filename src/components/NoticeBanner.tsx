/**
 * Persistent MUI Alert under the AppBar lock banner, or a Snackbar for errors.
 *
 * Empty notice renders nothing. Error and warning use role=alert.
 * Success and info use role=status. An error is a Snackbar that stays
 * until dismiss. Other severities stay under the lock bar.
 */

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Snackbar from "@mui/material/Snackbar";
import { useNotice } from "../containers/NoticeContext";
import { t } from "../lib/i18n";

/**
 * App-wide action-flash banner.
 *
 * @returns The Alert, a Snackbar wrapping it for errors, or null.
 */
export function NoticeBanner() {
  const { notice, dismiss } = useNotice();
  if (!notice) return null;
  const assertive = notice.severity === "error" || notice.severity === "warning";
  const alert = (
    <Alert
      id="app-notice"
      severity={notice.severity}
      role={assertive ? "alert" : "status"}
      onClose={dismiss}
      slotProps={{
        closeButton: { "aria-label": t("common.close") },
      }}
    >
      {notice.text}
    </Alert>
  );
  if (notice.severity === "error") {
    return (
      <Snackbar
        open
        autoHideDuration={null}
        onClose={dismiss}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        {alert}
      </Snackbar>
    );
  }
  return (
    <Box sx={{ px: 2, py: 1, flexShrink: 0 }}>
      {alert}
    </Box>
  );
}
