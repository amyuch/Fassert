`default_nettype none
module testbench(input clock, input reset);
	reg pcpi_valid;
	reg [31:0] pcpi_insn, pcpi_rs1, pcpi_rs2;
	wire [31:0] pcpi_rd;
	wire pcpi_wr, pcpi_wait, pcpi_ready;

	picorv32_pcpi_mul dut (
		.clk(clock), .resetn(!reset),
		.pcpi_valid(pcpi_valid), .pcpi_insn(pcpi_insn),
		.pcpi_rs1(pcpi_rs1), .pcpi_rs2(pcpi_rs2),
		.pcpi_wr(pcpi_wr), .pcpi_rd(pcpi_rd),
		.pcpi_wait(pcpi_wait), .pcpi_ready(pcpi_ready));

	// plain shift-add accumulator over the RTL's own shift registers
	reg [63:0] m_acc;
	always @(posedge clock) begin
		if (reset) m_acc <= 0;
		else if (dut.mul_waiting) m_acc <= 0;
		else m_acc <= m_acc + (dut.rs1[0] ? dut.rs2 : 64'd0);
	end
	always @(posedge clock) begin
		if (!reset) begin
			if (dut.mul_finish)
				h_contract: assert((dut.rd + dut.rdx) == m_acc);
		end
	end
endmodule
