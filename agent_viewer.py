import tkinter as tk
from tkinter import ttk, messagebox
from registry import registry

class AgentViewer:
    def __init__(self, root):
        self.root = root
        self.root.title("Agent Manager")
        self.root.geometry("800x500")

        self.setup_ui()
        self.refresh_data()

    def setup_ui(self):
        # Control Panel
        control_frame = ttk.Frame(self.root, padding="10")
        control_frame.pack(fill=tk.X)

        ttk.Label(control_frame, text="Available Agents", font=("Arial", 14, "bold")).pack(side=tk.LEFT)
        ttk.Button(control_frame, text="Refresh", command=self.refresh_data).pack(side=tk.RIGHT, padx=5)
        ttk.Button(control_frame, text="Delete Selected", command=self.delete_agent).pack(side=tk.RIGHT, padx=5)

        # Table
        table_frame = ttk.Frame(self.root, padding="10")
        table_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("id", "name", "specialization", "is_head")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings")

        for col in columns:
            self.tree.heading(col, text=col.capitalize())
        
        self.tree.column("id", width=150)
        self.tree.column("name", width=150)
        self.tree.column("specialization", width=300)
        self.tree.column("is_head", width=100)

        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def refresh_data(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for agent in registry.list_agents():
            self.tree.insert("", tk.END, values=(
                agent.agent_id,
                agent.persona_name,
                ", ".join(agent.specialization),
                str(agent.is_head_agent)
            ))

    def delete_agent(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showwarning("Selection Required", "Please select an agent to delete.")
            return

        agent_id = self.tree.item(selected_item)['values'][0]

        if registry.get_agent(agent_id).is_head_agent:
            messagebox.showerror("Error", "Cannot delete the head agent (nexus_prime).")
            return

        confirm = messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete agent: {agent_id}?\nThis action cannot be undone.")
        
        if confirm:
            registry.delete_agent(agent_id)
            messagebox.showinfo("Deleted", f"Agent {agent_id} successfully removed.")
            self.refresh_data()

if __name__ == "__main__":
    root = tk.Tk()
    app = AgentViewer(root)
    root.mainloop()
