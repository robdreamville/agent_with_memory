import tkinter as tk
from tkinter import ttk, messagebox
import chromadb
import config

class VaultViewer:
    def __init__(self, root):
        self.root = root
        self.root.title("Memory Bank")
        self.root.geometry("900x650") # Slightly taller to accommodate the button

        # ChromaDB Client
        try:
            self.client = chromadb.PersistentClient(path=config.CHROMA_DB_PATH)
            self.collection = self.client.get_or_create_collection("permanent_vault")
        except Exception as e:
            messagebox.showerror("Error", f"Could not connect to ChromaDB: {e}")
            self.root.destroy()
            return

        self.setup_ui()
        self.refresh_data()

    def setup_ui(self):
        # Top Control Panel
        control_frame = ttk.Frame(self.root, padding="10")
        control_frame.pack(fill=tk.X)

        ttk.Label(control_frame, text="Permanent Vault Records", font=("Arial", 14, "bold")).pack(side=tk.LEFT)
        ttk.Button(control_frame, text="Refresh", command=self.refresh_data).pack(side=tk.RIGHT, padx=5)
        
        # ADDED: Delete Button in the top bar
        ttk.Button(control_frame, text="Delete Selected", command=self.delete_memory).pack(side=tk.RIGHT, padx=5)

        # Table (Treeview)
        table_frame = ttk.Frame(self.root, padding="10")
        table_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("id", "content", "owner", "visibility", "tags", "importance_score")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings")

        # Column Headings
        for col in columns:
            # Capitalize and replace underscores with spaces
            self.tree.heading(col, text=col.replace('_', ' ').title())
        
        self.tree.column("id", width=100)
        self.tree.column("content", width=350)
        self.tree.column("owner", width=100)
        self.tree.column("visibility", width=80)
        self.tree.column("tags", width=120)
        self.tree.column("importance_score", width=100)

        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Detail Panel
        detail_frame = ttk.LabelFrame(self.root, text="Record Detail", padding="10")
        detail_frame.pack(fill=tk.X, padx=10, pady=10)

        self.detail_text = tk.Text(detail_frame, height=6, wrap=tk.WORD, state=tk.DISABLED, bg="#f0f0f0")
        self.detail_text.pack(fill=tk.X)

        self.tree.bind("<<TreeviewSelect>>", self.show_detail)

    def refresh_data(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        try:
            data = self.collection.get()
            for i in range(len(data['ids'])):
                meta = data['metadatas'][i] if data['metadatas'] else {}
                self.tree.insert("", tk.END, values=(
                    data['ids'][i],
                    data['documents'][i],
                    meta.get('owner_id', 'N/A'),
                    meta.get('visibility', 'N/A'),
                    meta.get('tags', meta.get('category', 'N/A')), # Fallback for old data
                    meta.get('importance_score', meta.get('importance', 'N/A')) # Fallback for old data
                ))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to fetch data: {e}")

    def show_detail(self, event):
        selected_item = self.tree.selection()
        if not selected_item:
            return

        item_values = self.tree.item(selected_item)['values']
        doc_id = str(item_values[0])

        data = self.collection.get(ids=[doc_id])
        if data['ids']:
            meta = data['metadatas'][0]
            content = data['documents'][0]
            
            detail_str = f"CONTENT: {content}\n\n"
            detail_str += f"RATIONALE: {meta.get('rationale', 'None provided')}\n"
            detail_str += f"TIMESTAMP: {meta.get('timestamp', 'N/A')}\n"
            detail_str += f"TAGS: {meta.get('tags', meta.get('category', 'N/A'))} | VISIBILITY: {meta.get('visibility', 'N/A')}"

            self.detail_text.config(state=tk.NORMAL)
            self.detail_text.delete(1.0, tk.END)
            self.detail_text.insert(tk.END, detail_str)
            self.detail_text.config(state=tk.DISABLED)

    # NEW: Method to handle deletion
    def delete_memory(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showwarning("Selection Required", "Please select a record to delete.")
            return

        item_values = self.tree.item(selected_item)['values']
        doc_id = str(item_values[0])

        # Confirmation dialog
        confirm = messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete record ID: {doc_id}?\nThis action cannot be undone.")
        
        if confirm:
            try:
                self.collection.delete(ids=[doc_id])
                messagebox.showinfo("Deleted", f"Record {doc_id} successfully removed.")
                self.refresh_data() # Refresh table to show it's gone
                self.detail_text.config(state=tk.NORMAL)
                self.detail_text.delete(1.0, tk.END)
                self.detail_text.config(state=tk.DISABLED)
            except Exception as e:
                messagebox.showerror("Deletion Error", f"Failed to delete record: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = VaultViewer(root)
    root.mainloop()