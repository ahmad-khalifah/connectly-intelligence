import { ROLE_LABEL } from "@/lib/api";
import { currentUser } from "@/lib/server";

import { UserMenuClient } from "./UserMenuClient";

export async function UserMenu() {
  const user = await currentUser();
  return (
    <UserMenuClient
      name={user.full_name}
      email={user.email}
      roleLabel={ROLE_LABEL[user.role]}
      isAdmin={user.role === "admin"}
    />
  );
}
