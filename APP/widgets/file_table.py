"""File table widget with status tracking."""

import os
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
from PySide6.QtGui import QColor
import qtawesome as qta


class FileTableWidget(QTableWidget):
    """Table widget untuk menampilkan daftar file dengan status."""
    
    file_selected = Signal(int, str)  # row index, file_path
    file_double_clicked = Signal(str)  # file_path for opening location
    
    STATUS_ICONS = {
        'pending': ('fa5s.clock', '#888888'),
        'processing': ('fa5s.spinner', '#FFA500'),
        'completed': ('fa5s.check-circle', '#4CAF50'),
        'failed': ('fa5s.times-circle', '#F44336'),
    }
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_table()
        self.file_data = {}  # row_index -> file_info dict
        
    def _setup_table(self):
        """Setup table properties."""
        self.setColumnCount(4)
        self.setHorizontalHeaderLabels(['No', 'Nama File', 'Ukuran', 'Status'])
        
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.SingleSelection)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        
        self.itemSelectionChanged.connect(self._on_selection_changed)
        self.itemDoubleClicked.connect(self._on_double_click)
        
    def add_file(self, file_path, file_id=None):
        """Add file to table."""
        row = self.rowCount()
        self.insertRow(row)
        
        file_name = os.path.basename(file_path)
        try:
            file_size = os.path.getsize(file_path)
            size_str = self._format_size(file_size)
        except:
            file_size = 0
            size_str = "N/A"
        
        self.file_data[row] = {
            'file_id': file_id,
            'file_path': file_path,
            'file_name': file_name,
            'file_size': file_size,
            'status': 'pending'
        }
        
        no_item = QTableWidgetItem(str(row + 1))
        no_item.setTextAlignment(Qt.AlignCenter)
        self.setItem(row, 0, no_item)
        
        name_item = QTableWidgetItem(file_name)
        self.setItem(row, 1, name_item)
        
        size_item = QTableWidgetItem(size_str)
        size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setItem(row, 2, size_item)
        
        status_item = QTableWidgetItem()
        icon_name, color = self.STATUS_ICONS['pending']
        status_item.setIcon(qta.icon(icon_name, color=color))
        status_item.setTextAlignment(Qt.AlignCenter)
        self.setItem(row, 3, status_item)
        
    def update_file_status(self, row, status):
        """Update status of a file."""
        if row < 0 or row >= self.rowCount():
            return
            
        self.file_data[row]['status'] = status
        
        status_item = self.item(row, 3)
        if status in self.STATUS_ICONS:
            icon_name, color = self.STATUS_ICONS[status]
            status_item.setIcon(qta.icon(icon_name, color=color))
        
        if status == 'processing':
            for col in range(self.columnCount()):
                item = self.item(row, col)
                if item:
                    item.setBackground(QColor(255, 255, 0, 13))  # Yellow with 0.05 opacity
        else:
            for col in range(self.columnCount()):
                item = self.item(row, col)
                if item:
                    item.setBackground(QColor(255, 255, 255, 0))  # Transparent
        
    def clear_all(self):
        """Clear all files from table."""
        self.setRowCount(0)
        self.file_data.clear()
    
    def get_file_path(self, row):
        """Get file path for a specific row."""
        return self.file_data.get(row, {}).get('file_path', '')
    
    def _format_size(self, size):
        """Format file size to human readable."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
    
    def _on_selection_changed(self):
        """Handle selection change."""
        selected_rows = self.selectionModel().selectedRows()
        if selected_rows:
            row = selected_rows[0].row()
            file_path = self.get_file_path(row)
            if file_path:
                self.file_selected.emit(row, file_path)
    
    def _on_double_click(self, item):
        """Handle double click to open file location."""
        row = item.row()
        file_path = self.get_file_path(row)
        if file_path:
            self.file_double_clicked.emit(file_path)
